"""Local HTTP interface for phase 2. One server process only."""

from contextlib import asynccontextmanager
from hashlib import sha256
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartException

from .audio import readiness
from .config import InputError, Settings
from .pipeline import Jobs, raw_text
from .schemas import MeetingView


class UploadLimit:
    """Enforce actual request bytes before multipart data can fill temporary storage."""

    def __init__(self, app, max_bytes):
        self.app, self.maximum = app, max_bytes + 65536

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST" or scope.get("path") != "/api/meetings":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
            if length < 0:
                raise ValueError
        except ValueError:
            return await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(scope, receive, send)
        if length > self.maximum:
            return await JSONResponse({"detail": "Request exceeds the upload size limit"}, status_code=413)(scope, receive, send)
        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > self.maximum:
                scope["metawispr.oversized"] = True
                # Starlette closes multipart temporary files on this exception.
                raise MultiPartException("Request exceeds the upload size limit")
            return message

        await self.app(scope, bounded_receive, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        app.state.jobs = Jobs(settings)
        try:
            yield
        finally:
            app.state.jobs.close()

    app = FastAPI(title="Metawispr", version="0.2.0", lifespan=lifespan)
    app.add_middleware(UploadLimit, max_bytes=settings.max_upload_bytes)

    def get_meeting(request, meeting_id):
        try:
            return request.app.state.jobs.runner.store.get(str(meeting_id))
        except FileNotFoundError:
            raise HTTPException(404, "Meeting not found")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "phase": "audio-and-transcription", **readiness(settings),
                "limits": {"upload_bytes": settings.max_upload_bytes,
                           "audio_seconds": settings.max_audio_seconds,
                           "pending_jobs": settings.max_pending_jobs}}

    @app.post("/api/meetings", status_code=202, openapi_extra={
        "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
            "type": "object", "required": ["file"], "additionalProperties": False,
            "properties": {"file": {"type": "string", "format": "binary"},
                           "title": {"type": "string", "maxLength": 200},
                           "glossary": {"type": "string", "maxLength": 10000}},
        }}}},
    })
    async def upload(request: Request):
        jobs = request.app.state.jobs
        if not jobs.slots.acquire(blocking=False):
            raise HTTPException(429, "The local processing queue is full. Try again after a recording finishes.")
        transferred = False
        meeting = None
        temporary = None
        try:
            if not request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
                raise HTTPException(415, "Upload a recording using multipart/form-data")
            async with request.form(max_files=1, max_fields=2, max_part_size=12000) as form:
                if set(form.keys()) - {"file", "title", "glossary"}:
                    raise HTTPException(422, "Allowed fields are file, title, and glossary")
                recording = form.get("file")
                title, glossary = form.get("title", ""), form.get("glossary", "")
                if not isinstance(recording, UploadFile) or not isinstance(title, str) or not isinstance(glossary, str):
                    raise HTTPException(422, "Provide one recording file and optional title/terminology text")
                if recording.size is not None and recording.size > settings.max_upload_bytes:
                    raise HTTPException(413, "Recording exceeds the upload size limit")
                meeting = jobs.runner.store.begin(recording.filename or "", title, glossary)
                directory = jobs.runner.store.directory(meeting.id)
                temporary = directory / "upload.partial"
                size, digest = 0, sha256()
                with temporary.open("wb") as destination:
                    while block := await recording.read(1024 * 1024):
                        size += len(block)
                        if size > settings.max_upload_bytes:
                            raise HTTPException(413, "Recording exceeds the upload size limit")
                        destination.write(block)
                        digest.update(block)
                if not size:
                    raise InputError("The uploaded recording is empty")
                temporary.replace(directory / meeting.source_name)
                meeting.size_bytes, meeting.input_sha256 = size, digest.hexdigest()
                jobs.runner.store.put(meeting)
                jobs.submit_reserved(meeting.id)
                transferred = True
                return meeting
        except StarletteHTTPException as exc:
            if request.scope.get("metawispr.oversized"):
                raise HTTPException(413, "Request exceeds the upload size limit") from exc
            raise
        except InputError as exc:
            raise HTTPException(422, str(exc)) from exc
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
            if not transferred:
                jobs.slots.release()
                if meeting:
                    meeting.stage, meeting.failed_stage = "failed", "queued"
                    meeting.error = "Upload did not finish. Submit the recording again."
                    jobs.runner.store.put(meeting)

    @app.get("/api/meetings")
    def meetings(request: Request):
        return {"meetings": request.app.state.jobs.runner.store.list()}

    @app.get("/api/meetings/{meeting_id}", response_model=MeetingView)
    def detail(request: Request, meeting_id: UUID):
        meeting = get_meeting(request, meeting_id)
        return MeetingView(meeting=meeting, raw=request.app.state.jobs.runner.store.raw(meeting.id))

    @app.post("/api/meetings/{meeting_id}/retry", status_code=202)
    def retry(request: Request, meeting_id: UUID):
        jobs = request.app.state.jobs
        with jobs.lock:
            meeting = get_meeting(request, meeting_id)
            if meeting.id in jobs.active or meeting.stage != "failed" or not meeting.retryable:
                raise HTTPException(409, "This recording is not eligible for retry")
            if not jobs.slots.acquire(blocking=False):
                raise HTTPException(429, "The local processing queue is full")
            try:
                meeting.stage, meeting.error, meeting.failed_stage = "queued", None, None
                jobs.runner.store.put(meeting)
            except Exception:
                jobs.slots.release()
                raise
        try:
            jobs.submit_reserved(meeting.id)
        except Exception:
            jobs.slots.release()
            raise
        return meeting

    @app.get("/api/meetings/{meeting_id}/audio")
    def audio(request: Request, meeting_id: UUID):
        meeting = get_meeting(request, meeting_id)
        path = request.app.state.jobs.runner.store.directory(meeting.id) / "prepared.wav"
        if not path.exists():
            raise HTTPException(409, "Prepared audio is not available yet")
        return FileResponse(path, media_type="audio/wav")

    @app.get("/api/meetings/{meeting_id}/export/{format}")
    def export(request: Request, meeting_id: UUID, format: str):
        meeting = get_meeting(request, meeting_id)
        raw = request.app.state.jobs.runner.store.raw(meeting.id)
        if format not in {"raw.txt", "raw.json"}:
            raise HTTPException(404, "Phase 2 provides raw.txt and raw.json exports")
        if raw is None:
            raise HTTPException(409, "The raw transcript is not available yet")
        headers = {"Content-Disposition": f'attachment; filename="{meeting.id}-{format}"'}
        if format == "raw.txt":
            return PlainTextResponse(raw_text(raw), headers=headers)
        return JSONResponse(raw.model_dump(mode="json"), headers=headers)

    return app


app = create_app()
