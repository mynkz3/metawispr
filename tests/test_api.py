from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from uuid import uuid4
import time
import unittest

from fastapi.testclient import TestClient

from metawispr.api import create_app
from metawispr.audio import file_sha256
from metawispr.config import Settings, SetupError
from metawispr.pipeline import Jobs, Runner
from support import FixtureASR, FixtureLLM, wav_bytes


def wait_for(client, meeting_id, stages=("complete", "failed")):
    for _ in range(200):
        response = client.get(f"/api/meetings/{meeting_id}")
        if response.json()["meeting"]["stage"] in stages:
            return response.json()
        time.sleep(0.01)
    raise AssertionError("test job did not reach its expected state")


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.settings = Settings(data_dir=self.root / "data", model_dir=self.root / "models",
                                 max_upload_bytes=100000)

    def test_upload_readback_audio_range_and_export_parity(self):
        app = create_app(self.settings)
        content = wav_bytes()
        with TestClient(app) as client:
            app.state.jobs.runner.asr = FixtureASR()
            app.state.jobs.runner.llm = FixtureLLM(self.settings)
            response = client.post("/api/meetings", files={"file": ("meeting.wav", content, "audio/wav")},
                                   data={"title": "Planning", "glossary": "ONNX"})
            self.assertEqual(response.status_code, 202)
            identifier = response.json()["id"]
            detail = wait_for(client, identifier)
            self.assertEqual(detail["meeting"]["stage"], "complete")
            self.assertEqual(detail["meeting"]["title"], "Planning")
            self.assertEqual(detail["meeting"]["glossary"], "ONNX")
            self.assertEqual(detail["raw"]["model"]["runtime"], "test-double")
            directory = self.settings.data_dir / identifier
            self.assertEqual((directory / "original.wav").read_bytes(), content)
            self.assertEqual((directory / "raw.json").read_text(encoding="utf-8").strip(),
                             app.state.jobs.runner.store.raw(identifier).model_dump_json(indent=2))
            audio = client.get(f"/api/meetings/{identifier}/audio", headers={"Range": "bytes=0-15"})
            self.assertEqual(audio.status_code, 206)
            self.assertEqual(audio.content, content[:16])
            exported = client.get(f"/api/meetings/{identifier}/export/raw.json")
            self.assertEqual(exported.json(), detail["raw"])
            text = client.get(f"/api/meetings/{identifier}/export/raw.txt").text
            self.assertEqual(text, detail["raw"]["segments"][0]["text"] + "\n")
            self.assertEqual(client.get("/api/meetings").json()["meetings"][0]["id"], identifier)
            with self.assertRaisesRegex(RuntimeError, "cannot be overwritten"):
                app.state.jobs.runner.store.save_raw(identifier, app.state.jobs.runner.store.raw(identifier))

    def test_rejected_uploads_do_not_leak_queue_slots(self):
        app = create_app(self.settings)
        with TestClient(app) as client:
            app.state.jobs.runner.asr = FixtureASR()
            app.state.jobs.runner.llm = FixtureLLM(self.settings)
            for filename, body in [("notes.txt", b"not audio"), ("empty.wav", b"")]:
                self.assertEqual(client.post("/api/meetings", files={"file": (filename, body)}).status_code, 422)
            self.assertEqual(client.post("/api/meetings", files={"file": ("a.wav", wav_bytes())},
                                         data={"glossary": "alias => Docker\nalias => Qwen"}).status_code, 422)
            self.assertEqual(client.post("/api/meetings", content=b"not multipart").status_code, 415)
            response = client.post("/api/meetings", files={"file": ("good.wav", wav_bytes())})
            self.assertEqual(response.status_code, 202)
            self.assertEqual(wait_for(client, response.json()["id"])["meeting"]["stage"], "complete")

    def test_polling_while_jobs_finish_keeps_checkpoints_readable(self):
        app = create_app(self.settings)
        with TestClient(app) as client:
            app.state.jobs.runner.asr = FixtureASR()
            app.state.jobs.runner.llm = FixtureLLM(self.settings)
            for _ in range(10):
                response = client.post("/api/meetings", files={"file": ("poll.wav", wav_bytes())})
                self.assertEqual(response.status_code, 202)
                detail = wait_for(client, response.json()["id"])
                self.assertEqual(detail["meeting"]["stage"], "complete")
                self.assertIsNotNone(detail["raw"])

    def test_oversized_body_is_rejected_with_and_without_content_length(self):
        settings = Settings(data_dir=self.root / "data", model_dir=self.root / "models", max_upload_bytes=20)
        with TestClient(create_app(settings)) as client:
            response = client.post("/api/meetings", files={"file": ("large.wav", b"x" * 70000)})
            self.assertEqual(response.status_code, 413)
            body = (b"--boundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"large.wav\"\r\n\r\n"
                    + b"x" * 70000 + b"\r\n--boundary--\r\n")
            response = client.post("/api/meetings", content=iter([body[:1000], body[1000:]]),
                                   headers={"Content-Type": "multipart/form-data; boundary=boundary"})
            self.assertEqual(response.status_code, 413)

    def test_additional_fields_and_second_file_are_rejected(self):
        with TestClient(create_app(self.settings)) as client:
            self.assertEqual(client.post("/api/meetings", files={"file": ("a.wav", wav_bytes())},
                                         data={"unexpected": "value"}).status_code, 422)
            response = client.post("/api/meetings", files=[("file", ("a.wav", wav_bytes())),
                                                           ("file", ("b.wav", wav_bytes()))])
            self.assertEqual(response.status_code, 400)

    def test_missing_model_retains_audio_and_reports_retryable_failure(self):
        app = create_app(self.settings)
        with TestClient(app) as client:
            response = client.post("/api/meetings", files={"file": ("a.wav", wav_bytes())})
            identifier = response.json()["id"]
            result = wait_for(client, identifier)
            self.assertEqual(result["meeting"]["stage"], "failed")
            self.assertEqual(result["meeting"]["failed_stage"], "transcribing")
            self.assertTrue(result["meeting"]["retryable"])
            self.assertIn("Parakeet", result["meeting"]["error"])
            self.assertIsNone(result["raw"])
            self.assertEqual(client.get(f"/api/meetings/{identifier}/audio").status_code, 200)
            self.assertEqual(client.get(f"/api/meetings/{identifier}/export/raw.txt").status_code, 409)
            self.assertFalse(client.get("/api/health").json()["transcription_ready"])
            app.state.jobs.runner.asr = FixtureASR()
            app.state.jobs.runner.llm = FixtureLLM(self.settings)
            prepared = self.settings.data_dir / identifier / "prepared.wav"
            before = prepared.stat().st_mtime_ns
            self.assertEqual(client.post(f"/api/meetings/{identifier}/retry").status_code, 202)
            self.assertEqual(wait_for(client, identifier)["meeting"]["stage"], "complete")
            self.assertEqual(prepared.stat().st_mtime_ns, before)
            self.assertEqual(client.post(f"/api/meetings/{identifier}/retry").status_code, 409)

    def test_silence_is_a_nonretryable_input_failure(self):
        with TestClient(create_app(self.settings)) as client:
            response = client.post("/api/meetings", files={"file": ("silence.wav", wav_bytes(silent=True))})
            identifier = response.json()["id"]
            result = wait_for(client, identifier)
            self.assertFalse(result["meeting"]["retryable"])
            self.assertIn("No speech", result["meeting"]["error"])
            self.assertEqual(client.post(f"/api/meetings/{identifier}/retry").status_code, 409)

    def test_full_queue_and_duplicate_retry_do_not_block_health(self):
        entered, release = Event(), Event()
        class BlockingASR(FixtureASR):
            def transcribe(self, *args, **kwargs):
                entered.set()
                if not release.wait(timeout=3):
                    raise SetupError("test timeout")
                return super().transcribe(*args, **kwargs)
        settings = Settings(data_dir=self.root / "data", model_dir=self.root / "models", max_pending_jobs=1)
        app = create_app(settings)
        with TestClient(app) as client:
            app.state.jobs.runner.asr = BlockingASR()
            app.state.jobs.runner.llm = FixtureLLM(settings)
            first = client.post("/api/meetings", files={"file": ("a.wav", wav_bytes())})
            identifier = first.json()["id"]
            try:
                self.assertTrue(entered.wait(timeout=2))
                self.assertEqual(client.post("/api/meetings", files={"file": ("b.wav", wav_bytes())}).status_code, 429)
                self.assertEqual(client.post(f"/api/meetings/{identifier}/retry").status_code, 409)
                self.assertEqual(client.get("/api/health").status_code, 200)
            finally:
                release.set()
            wait_for(client, identifier)

    def test_missing_ids_and_unavailable_artifacts_are_clear(self):
        with TestClient(create_app(self.settings)) as client:
            self.assertEqual(client.get(f"/api/meetings/{uuid4()}").status_code, 404)
            self.assertEqual(client.get("/api/meetings/not-a-uuid").status_code, 422)
            schema = client.get("/openapi.json").json()
            upload_schema = schema["paths"]["/api/meetings"]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]
            self.assertEqual(upload_schema["properties"]["file"]["format"], "binary")

    def test_startup_recovers_interrupted_status_without_inventing_completion(self):
        runner = Runner(self.settings)
        meeting = runner.store.begin("a.wav")
        source = runner.store.directory(meeting.id) / meeting.source_name
        source.write_bytes(wav_bytes())
        meeting.input_sha256 = file_sha256(source)
        meeting.stage = "transcribing"
        runner.store.put(meeting)
        jobs = Jobs(self.settings)
        self.addCleanup(jobs.close)
        recovered = jobs.runner.store.get(meeting.id)
        self.assertEqual(recovered.stage, "failed")
        self.assertEqual(recovered.failed_stage, "transcribing")
        self.assertTrue(recovered.retryable)
        self.assertIsNone(recovered.transcribed_at)


if __name__ == "__main__":
    unittest.main()
