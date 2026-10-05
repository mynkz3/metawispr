"""Per-meeting checkpoints and one bounded local inference worker."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import BoundedSemaphore, Lock
from uuid import UUID, uuid4
import json
import logging
import os
import tempfile
import time
import gc

from .audio import Parakeet, file_sha256, inspect_pcm, prepare_audio
from .config import InputError, Settings, SetupError, SUPPORTED_SUFFIXES
from .schemas import Meeting, RawTranscript, RefinedTranscript, DocumentedMeeting
from .llm import Ollama, digest
from .documentation import Documentation, apply_edits, validate_record, refinement_policy, documentation_policy, glossary_terms


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, delete=False) as target:
            temporary = Path(target.name)
            target.write(text)
            target.flush()
            os.fsync(target.fileno())
        temporary.replace(path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def raw_text(raw: RawTranscript) -> str:
    return "\n".join(segment.text for segment in raw.segments) + "\n"


class Store:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.data_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        # Windows cannot replace a checkpoint while another thread holds it open.
        self.io_lock = Lock()

    def directory(self, meeting_id: str) -> Path:
        canonical = str(UUID(meeting_id))
        directory = self.root / canonical
        if not directory.resolve().is_relative_to(self.root):
            raise ValueError("Invalid meeting path")
        return directory

    def get(self, meeting_id: str) -> Meeting:
        with self.io_lock:
            return Meeting.model_validate_json((self.directory(meeting_id) / "meeting.json").read_text(encoding="utf-8"))

    def put(self, meeting: Meeting):
        with self.io_lock:
            meeting.updated_at = now()
            atomic_write(self.directory(meeting.id) / "meeting.json", meeting.model_dump_json(indent=2))

    def begin(self, filename: str, title: str = "", glossary: str = "") -> Meeting:
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise InputError("Use a WAV, MP3, M4A, FLAC, OGG, or WEBM recording.")
        title = title.strip() or Path(filename).stem or "Untitled meeting"
        if len(title) > 200 or len(glossary) > 10000:
            raise InputError("Title is limited to 200 characters and terminology to 10,000 characters.")
        glossary_terms(glossary)
        identifier = str(uuid4())
        self.directory(identifier).mkdir()
        meeting = Meeting(id=identifier, title=title, filename=filename,
                          source_name=f"original{suffix}", glossary=glossary,
                          created_at=now(), updated_at=now(), stage="queued")
        self.put(meeting)
        return meeting

    def list(self, limit=50) -> list[Meeting]:
        # ponytail: a directory scan suits local use; use a shared job store for a hosted service.
        meetings = []
        for path in self.root.glob("*/meeting.json"):
            try:
                meetings.append(self.get(path.parent.name))
            except (ValueError, OSError):
                logging.warning("Skipping an unreadable meeting checkpoint")
        return sorted(meetings, key=lambda item: item.created_at, reverse=True)[:limit]

    def raw(self, meeting_id: str) -> RawTranscript | None:
        with self.io_lock:
            path = self.directory(meeting_id) / "raw.json"
            if not path.exists():
                return None
            return RawTranscript.model_validate_json(path.read_text(encoding="utf-8"))

    def save_raw(self, meeting_id: str, raw: RawTranscript):
        with self.io_lock:
            directory = self.directory(meeting_id)
            if (directory / "raw.json").exists():
                raise RuntimeError("A saved raw transcript cannot be overwritten")
            atomic_write(directory / "raw.json", raw.model_dump_json(indent=2))
            atomic_write(directory / "raw.txt", raw_text(raw))

    def read_json(self, meeting_id, filename):
        with self.io_lock:
            path = self.directory(meeting_id) / filename
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def write_json(self, meeting_id, filename, value):
        with self.io_lock:
            atomic_write(self.directory(meeting_id) / filename, json.dumps(value, ensure_ascii=False, indent=2))

    def refined(self, meeting_id):
        saved = self.read_json(meeting_id, "refined.json")
        if saved is None:
            return None
        result = RefinedTranscript.model_validate(saved)
        raw, meeting = self.raw(meeting_id), self.get(meeting_id)
        if raw is None or result.source_sha256 != digest(raw.model_dump()):
            raise SetupError("Refined checkpoint does not match the raw transcript.")
        segments, accepted, rejected = apply_edits(raw.segments, result.accepted, meeting.glossary)
        if rejected or accepted != result.accepted or segments != result.segments:
            raise SetupError("Refined checkpoint fails edit validation.")
        return result

    def document(self, meeting_id):
        saved = self.read_json(meeting_id, "document.json")
        if saved is None:
            return None
        result = DocumentedMeeting.model_validate(saved)
        refined = self.refined(meeting_id)
        if refined is None or result.source_sha256 != digest(refined.model_dump()):
            raise SetupError("Documentation checkpoint does not match the refined transcript.")
        validate_record(result.record, refined.segments, result.revision_audit)
        return result


class Runner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = Store(settings)
        self.asr = Parakeet(settings)
        self.llm = Ollama(settings)

    def run(self, meeting_id: str):
        meeting = self.store.get(meeting_id)
        directory = self.store.directory(meeting_id)
        try:
            source = directory / meeting.source_name
            if not source.is_file() or file_sha256(source) != meeting.input_sha256:
                raise InputError("The original recording is missing or changed. Upload it as a new meeting.")
            existing = self.store.raw(meeting_id)
            if existing:
                if existing.input_sha256 != meeting.input_sha256:
                    raise InputError("The saved transcript belongs to a different recording.")
                prepared = directory / "prepared.wav"
                if not prepared.is_file() or file_sha256(prepared) != existing.audio_sha256:
                    raise InputError("The prepared audio is missing or changed. Upload the original as a new meeting.")
                atomic_write(directory / "raw.txt", raw_text(existing))
                meeting.stage = "transcribed"
                meeting.transcribed_at = existing.created_at
                meeting.duration_seconds = existing.duration_seconds
                meeting.processed_audio_seconds = existing.duration_seconds
                meeting.error, meeting.failed_stage, meeting.retryable = None, None, False
                self.store.put(meeting)
            else:
                meeting.stage = "preparing"
                meeting.error, meeting.failed_stage, meeting.retryable = None, None, False
                self.store.put(meeting)
                prepared = directory / "prepared.wav"
                started = time.perf_counter()
                if prepared.exists():
                    meeting.duration_seconds = inspect_pcm(prepared, self.settings.max_audio_seconds)
                else:
                    meeting.duration_seconds = prepare_audio(source, prepared, self.settings)
                    meeting.prepare_seconds = time.perf_counter() - started
                meeting.stage = "transcribing"
                meeting.processed_audio_seconds = 0.0
                self.store.put(meeting)

                def progress(seconds):
                    meeting.processed_audio_seconds = seconds
                    self.store.put(meeting)

                raw = self.asr.transcribe(prepared, meeting.input_sha256, now(), progress)
                self.store.save_raw(meeting_id, raw)
                meeting.stage = "transcribed"
                meeting.transcribed_at = raw.created_at
                self.store.put(meeting)
            if meeting.target == "transcribed":
                return
            # Release native ASR weights before loading either LLM.
            if isinstance(self.asr, Parakeet):
                self.asr.recognizer = None
                gc.collect()
            raw = self.store.raw(meeting_id)
            worker = Documentation(self.settings, self.store, self.llm)

            def llm_progress(count):
                meeting.llm_completed_calls = count
                self.store.put(meeting)

            meeting.stage = "refining"
            meeting.llm_completed_calls = 0
            self.store.put(meeting)
            refined = self.store.refined(meeting_id)
            models = None
            if refined is None:
                models = self.llm.models()
                refined = worker.refine(meeting, raw, models[0], llm_progress)
                self.store.write_json(meeting_id, "refined.json", refined.model_dump())
            elif refined.policy_sha256 != refinement_policy(self.settings, meeting.glossary):
                raise SetupError("Refinement policy changed. Restore its model/glossary/prompt settings or submit a new meeting.")
            meeting.refined_at = refined.created_at
            meeting.stage = "documenting"
            meeting.llm_completed_calls = 0
            self.store.put(meeting)
            document = self.store.document(meeting_id)
            if document is None:
                models = models or self.llm.models()
                document = worker.document(meeting, refined, models[1], llm_progress)
                self.store.write_json(meeting_id, "document.json", document.model_dump())
            elif document.policy_sha256 != documentation_policy(self.settings):
                raise SetupError("Documentation policy changed. Restore its model/prompt settings or submit a new meeting.")
            meeting.documented_at = document.created_at
            meeting.llm_completed_calls = len(document.calls)
            meeting.stage = "complete"
            meeting.error, meeting.failed_stage, meeting.retryable = None, None, False
            self.store.put(meeting)
        except Exception as exc:
            failed_stage = meeting.stage
            meeting.stage = "failed"
            meeting.failed_stage = failed_stage
            meeting.retryable = not isinstance(exc, InputError)
            meeting.error = str(exc) if isinstance(exc, (InputError, SetupError)) else "Processing failed. Check the server log, then retry."
            self.store.put(meeting)
            if not isinstance(exc, (InputError, SetupError)):
                logging.exception("Meeting processing failed")


class Jobs:
    """One inference thread and a reservation covering uploads, queued and active jobs."""

    def __init__(self, settings: Settings):
        self.runner = Runner(settings)
        self.slots = BoundedSemaphore(settings.max_pending_jobs)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="metawispr")
        self.lock = Lock()
        self.active = set()
        for meeting in self.runner.store.list(limit=10**9):
            if meeting.stage in {"queued", "preparing", "transcribing", "refining", "documenting"}:
                meeting.failed_stage, meeting.stage = meeting.stage, "failed"
                meeting.retryable = (self.runner.store.directory(meeting.id) / meeting.source_name).is_file()
                meeting.error = "Processing was interrupted. Retry to resume saved stages."
                self.runner.store.put(meeting)

    def submit_reserved(self, meeting_id: str):
        with self.lock:
            if meeting_id in self.active:
                raise RuntimeError("This recording is already being processed")
            self.active.add(meeting_id)
        try:
            future = self.executor.submit(self.runner.run, meeting_id)
        except Exception:
            with self.lock:
                self.active.remove(meeting_id)
            raise

        def finished(result):
            with self.lock:
                self.active.remove(meeting_id)
            self.slots.release()
            if not result.cancelled() and result.exception() is not None:
                exception = result.exception()
                logging.error("Worker could not save meeting %s", meeting_id,
                              exc_info=(type(exception), exception, exception.__traceback__))

        future.add_done_callback(finished)

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)
