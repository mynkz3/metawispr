from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile
import json
import unittest

from fastapi.testclient import TestClient

from metawispr.api import create_app
from metawispr.audio import file_sha256
from metawispr.config import Settings, SetupError
from metawispr.documentation import Documentation
from metawispr.llm import digest
from metawispr.pipeline import Jobs, Runner
from metawispr.schemas import DocumentationBatch, Evidence, Fact, MeetingRecord, Segment, Task
from support import FixtureASR, FixtureLLM, wav_bytes
from test_api import wait_for


class Phase3Tests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.settings = Settings(data_dir=Path(self.folder.name) / "data")

    def test_bounded_notes_compression_preserves_canonical_task_and_source(self):
        runner, meeting = self.runner_and_meeting()
        raw = FixtureASR().transcribe(runner.store.directory(meeting.id) / meeting.source_name,
                                      meeting.input_sha256, "fixture")
        raw.duration_seconds = 20.0
        raw.segments = [Segment(id="s1", start=0.0, end=10.0, text="Maya will send the report by Friday."),
                        Segment(id="s2", start=10.0, end=20.0, text="Production cost is twelve fifty.")]
        llm = runner.llm
        worker = Documentation(self.settings, runner.store, llm)
        refined = worker.refine(meeting, raw, llm.models()[0], lambda count: None)
        brief_calls = []
        def request(method, path, body=None, timeout=None):
            payload = json.loads(body["messages"][1]["content"])
            properties = body["format"]["properties"]
            if "segments" in payload:
                source = payload["segments"][0]
                evidence = [source["id"]]
                if "tasks" in properties:
                    tasks = ([{"text": "Send the report", "owner": "Maya", "deadline": "Friday",
                               "evidence_ids": evidence}] if source["id"] == "s1:u000" else [])
                    output = {"tasks": tasks, "decisions": [], "revisions": []}
                else:
                    output = {"summary": [{"text": f"Explicit long fixture point {i}", "evidence_ids": evidence}
                                           for i in range(3)], "topics": [], "uncertainties": []}
                    if source["id"] == "s2:u000":
                        output["summary"][0]["text"] = "Production cost is twelve fifty."
            elif "candidates" in payload:
                output = {"resolutions": [{"candidate_id": item["candidate_id"], "disposition": "keep",
                                           "replacement": None, "reason": "Still assigned",
                                           "evidence_ids": item["fact"]["evidence_ids"]}
                                          for item in payload["candidates"]]}
            else:
                if len(payload["chronological_batches"]) == 1:
                    brief_calls.append(payload)
                output = {"summary_ids": [batch["summary_ids"][0] for batch in payload["chronological_batches"]],
                          "topics": [], "uncertainty_ids": []}
            return {"done": True, "done_reason": "stop", "message": {"content": json.dumps(output)}}
        original_fits = llm.fits
        def fits(name, contract, payload, feedback=""):
            if name == "document" and len(payload.get("segments", [])) > 1:
                return False
            if (name == "consolidate" and len(payload["chronological_batches"]) > 1 and
                    any(len(batch["summary_ids"]) > 1 for batch in payload["chronological_batches"])):
                return False
            return original_fits(name, contract, payload, feedback)
        with patch.object(llm, "request", side_effect=request), patch.object(llm, "fits", side_effect=fits):
            result = worker.document(meeting, refined, llm.models()[1], lambda count: None)
        self.assertEqual(len(brief_calls), 2)
        self.assertEqual(len(result.record.tasks), 1)
        self.assertEqual((result.record.tasks[0].owner, result.record.tasks[0].deadline), ("Maya", "Friday"))
        self.assertEqual(result.record.tasks[0].evidence[0].quote, raw.segments[0].text)
        self.assertEqual(raw.segments[0].text, "Maya will send the report by Friday.")
        self.assertEqual(result.record.summary[1].text, "Production cost is twelve fifty.")
        self.assertEqual(result.record.summary[1].evidence[0].quote, raw.segments[1].text)

    def test_oversized_review_draft_splits_source_without_dropping_any_unit(self):
        runner, meeting = self.runner_and_meeting()
        raw = FixtureASR().transcribe(runner.store.directory(meeting.id) / meeting.source_name,
                                      meeting.input_sha256, "fixture")
        raw.duration_seconds = 20.0
        raw.segments = [Segment(id="s1", start=0.0, end=10.0, text="First source window."),
                        Segment(id="s2", start=10.0, end=20.0, text="Second source window.")]
        llm = runner.llm
        worker = Documentation(self.settings, runner.store, llm)
        refined = worker.refine(meeting, raw, llm.models()[0], lambda count: None)
        original_fits = llm.fits
        def fits(name, contract, payload, feedback=""):
            return not (name == "review" and len(payload["segments"]) > 1) and original_fits(name, contract, payload, feedback)
        with patch.object(llm, "fits", side_effect=fits):
            result = worker.document(meeting, refined, llm.models()[1], lambda count: None)
        quotes = {ev.quote for fact in result.record.summary for ev in fact.evidence}
        self.assertEqual(quotes, {segment.text for segment in raw.segments})
        reviews = [json.loads(body["messages"][1]["content"]) for _, body in llm.requests
                   if "draft" in json.loads(body["messages"][1]["content"])]
        self.assertEqual(len(reviews), 2)
        self.assertTrue(all(len(payload["segments"]) == 1 for payload in reviews))

    def runner_and_meeting(self):
        runner = Runner(self.settings)
        runner.asr, runner.llm = FixtureASR(), FixtureLLM(self.settings)
        meeting = runner.store.begin("fixture.wav")
        source = runner.store.directory(meeting.id) / meeting.source_name
        source.write_bytes(wav_bytes())
        meeting.input_sha256 = file_sha256(source)
        runner.store.put(meeting)
        return runner, meeting

    def test_document_failure_retry_reuses_raw_refinement_and_calls(self):
        runner, meeting = self.runner_and_meeting()
        runner.llm.fail_document = True
        runner.run(meeting.id)
        failed = runner.store.get(meeting.id)
        self.assertEqual((failed.stage, failed.failed_stage), ("failed", "documenting"))
        self.assertTrue(failed.retryable)
        directory = runner.store.directory(meeting.id)
        original = {name: (directory / name).read_bytes() for name in ("raw.json", "refined.json", "original.wav")}
        runner.llm.fail_document = False
        with patch.object(runner.asr, "transcribe", side_effect=AssertionError("ASR must not rerun")):
            runner.run(meeting.id)
        self.assertEqual(runner.store.get(meeting.id).stage, "complete")
        for name, content in original.items():
            self.assertEqual((directory / name).read_bytes(), content)
        refine_calls = [body for _, body in runner.llm.requests if "edits" in body["format"]["properties"]]
        self.assertEqual(len(refine_calls), 1)
        self.assertEqual(runner.llm.unloaded, [self.settings.refiner_model, self.settings.documenter_model,
                                              self.settings.documenter_model])

    def test_shared_weights_keep_separate_validated_stage_checkpoints(self):
        runner, meeting = self.runner_and_meeting()
        runner.run(meeting.id)
        self.assertEqual(runner.store.get(meeting.id).stage, "complete")
        refined = runner.store.refined(meeting.id)
        document = runner.store.document(meeting.id)
        self.assertEqual(refined.calls[0].model, document.calls[0].model)
        self.assertNotEqual(refined.calls[0].prompt_sha256, document.calls[0].prompt_sha256)
        self.assertNotEqual(refined.calls[0].key, document.calls[0].key)
        directory = runner.store.directory(meeting.id)
        self.assertTrue((directory / "refining" / "calls" / f"{refined.calls[0].key}.json").is_file())
        self.assertTrue((directory / "documenting" / "calls" / f"{document.calls[0].key}.json").is_file())

    def test_completed_record_does_not_need_a_model_server_to_resume(self):
        runner, meeting = self.runner_and_meeting()
        runner.run(meeting.id)
        saved = runner.store.get(meeting.id)
        saved.refined_at, saved.documented_at = None, None
        runner.store.put(saved)
        with patch.object(runner.llm, "models", side_effect=AssertionError("no model request")):
            runner.run(meeting.id)
        self.assertEqual(runner.store.get(meeting.id).stage, "complete")
        self.assertEqual(runner.store.get(meeting.id).refined_at, runner.store.refined(meeting.id).created_at)
        self.assertEqual(runner.store.get(meeting.id).documented_at, runner.store.document(meeting.id).created_at)

    def test_changed_prepared_audio_cannot_be_used_as_transcript_evidence(self):
        runner, meeting = self.runner_and_meeting()
        runner.run(meeting.id)
        prepared = runner.store.directory(meeting.id) / "prepared.wav"
        prepared.write_bytes(wav_bytes(seconds=0.5))
        runner.run(meeting.id)
        result = runner.store.get(meeting.id)
        self.assertEqual(result.stage, "failed")
        self.assertFalse(result.retryable)
        self.assertIn("prepared audio", result.error)

    def test_llm_anchors_are_resolved_only_when_unique(self):
        runner, meeting = self.runner_and_meeting()
        source = runner.store.directory(meeting.id) / meeting.source_name
        raw = FixtureASR().transcribe(source, meeting.input_sha256, "fixture")
        raw.segments[0].text = "Use dock her."
        response = {"done": True, "done_reason": "stop", "message": {"content": json.dumps({"edits": [
            {"segment_id": "s00001", "original": "dock her", "replacement": "Docker", "reason": "fixture"}]})}}
        meeting.glossary = "Docker"
        worker = Documentation(self.settings, runner.store, runner.llm)
        with patch.object(runner.llm, "request", return_value=response):
            result = worker.refine(meeting, raw, runner.llm.models()[0], lambda count: None)
            self.assertEqual(result.segments[0].text, "Use Docker.")
            self.assertEqual((result.accepted[0].start, result.accepted[0].end), (4, 12))
            raw.segments[0].text = "Use dock her, then dock her."
            result = worker.refine(meeting, raw, runner.llm.models()[0], lambda count: None)
            self.assertEqual(result.accepted, [])
            self.assertEqual(result.rejected[0].rejection, "Original anchor is absent or ambiguous")

    def test_changed_source_is_rejected_without_replacing_raw(self):
        runner, meeting = self.runner_and_meeting()
        runner.run(meeting.id)
        source = runner.store.directory(meeting.id) / meeting.source_name
        source.write_bytes(b"changed")
        runner.run(meeting.id)
        self.assertFalse(runner.store.get(meeting.id).retryable)
        self.assertIn("missing or changed", runner.store.get(meeting.id).error)

    def test_interrupted_llm_stages_recover_as_retryable(self):
        runner, meeting = self.runner_and_meeting()
        for stage in ("refining", "documenting"):
            meeting.stage = stage
            runner.store.put(meeting)
            jobs = Jobs(self.settings)
            try:
                saved = jobs.runner.store.get(meeting.id)
                self.assertEqual(saved.failed_stage, stage)
                self.assertTrue(saved.retryable)
            finally:
                jobs.close()

    def test_api_can_document_an_existing_asr_checkpoint_without_retranscribing(self):
        app = create_app(self.settings)
        with TestClient(app) as client:
            runner = app.state.jobs.runner
            runner.asr, runner.llm = FixtureASR(), FixtureLLM(self.settings)
            meeting = runner.store.begin("fixture.wav")
            source = runner.store.directory(meeting.id) / meeting.source_name
            source.write_bytes(wav_bytes())
            meeting.input_sha256, meeting.target = file_sha256(source), "transcribed"
            runner.store.put(meeting)
            runner.run(meeting.id)
            before = runner.store.raw(meeting.id).model_dump_json()
            with patch.object(runner.asr, "transcribe", side_effect=AssertionError("ASR must not run")):
                self.assertEqual(client.post(f"/api/meetings/{meeting.id}/document").status_code, 202)
                self.assertEqual(wait_for(client, meeting.id)["meeting"]["stage"], "complete")
            self.assertEqual(runner.store.raw(meeting.id).model_dump_json(), before)

    def test_api_exports_all_use_the_canonical_record_and_no_model_calls(self):
        app = create_app(self.settings)
        with TestClient(app) as client:
            runner = app.state.jobs.runner
            runner.asr, runner.llm = FixtureASR(), FixtureLLM(self.settings)
            response = client.post("/api/meetings", files={"file": ("fixture.wav", wav_bytes())})
            identifier = response.json()["id"]
            result = wait_for(client, identifier)
            self.assertEqual(result["meeting"]["stage"], "complete")
            before = len(runner.llm.requests)
            exported = client.get(f"/api/meetings/{identifier}/export/meeting.json").json()
            self.assertEqual(exported["record"], result["document"]["record"])
            zipped = client.get(f"/api/meetings/{identifier}/export/bundle.zip")
            with ZipFile(BytesIO(zipped.content)) as archive:
                self.assertEqual(json.loads(archive.read("meeting.json"))["record"], exported["record"])
                self.assertEqual(archive.read("meeting.md"), client.get(
                    f"/api/meetings/{identifier}/export/meeting.md").content)
                self.assertEqual(archive.read("raw.txt"), client.get(f"/api/meetings/{identifier}/export/raw.txt").content)
            self.assertEqual(len(runner.llm.requests), before)
            self.assertEqual(client.get(f"/api/meetings/{identifier}/export/unknown").status_code, 404)
            broken = runner.store.document(identifier).model_dump()
            broken["source_sha256"] = "changed"
            runner.store.write_json(identifier, "document.json", broken)
            self.assertEqual(client.get(f"/api/meetings/{identifier}/export/raw.txt").status_code, 200)
            self.assertEqual(client.get(f"/api/meetings/{identifier}/export/refined.txt").status_code, 200)
            self.assertEqual(client.get(f"/api/meetings/{identifier}/export/meeting.json").status_code, 409)

    def test_later_revision_reaches_chronological_consolidation_and_map_calls_resume(self):
        runner, meeting = self.runner_and_meeting()
        raw = FixtureASR().transcribe(runner.store.directory(meeting.id) / meeting.source_name,
                                      meeting.input_sha256, "fixture")
        raw.duration_seconds = 20.0
        raw.segments = [Segment(id="s1", start=0.0, end=10.0, text="We agree to deploy Friday."),
                        Segment(id="s2", start=10.0, end=20.0, text="Cancel the Friday deployment.")]
        llm = runner.llm
        worker = Documentation(self.settings, runner.store, llm)
        refined = worker.refine(meeting, raw, llm.models()[0], lambda count: None)
        consolidation_inputs = []
        reconciliation_inputs = []
        attempts = [0]
        def request(method, path, body=None, timeout=None):
            payload = json.loads(body["messages"][1]["content"])
            value = {"summary": [], "topics": [], "decisions": [], "tasks": [], "uncertainties": []}
            revisions = []
            if "segments" in payload:
                segment = payload["segments"][0]
                fact = {"text": segment["text"], "evidence_ids": [segment["id"]]}
                if segment["id"] == "s1:u000":
                    value["decisions"] = [fact]
                else:
                    revisions = [fact]
                if "resolved_current" in payload:
                    return {"done": True, "done_reason": "stop", "message": {"content": json.dumps(
                        {key: value[key] for key in ("summary", "topics", "uncertainties")})}}
            elif "candidates" in payload:
                reconciliation_inputs.append(payload)
                output = {"resolutions": [{"candidate_id": item["candidate_id"], "disposition": "retire",
                                             "replacement": None, "reason": "Friday deployment cancelled",
                                             "evidence_ids": ["s2:u000"]}
                                            for item in payload["candidates"]]}
                return {"done": True, "done_reason": "stop", "message": {"content": json.dumps(output)}}
            else:
                consolidation_inputs.append(payload)
                attempts[0] += 1
                if attempts[0] == 1:
                    raise SetupError("Explicit interrupted consolidation fixture")
                return {"done": True, "done_reason": "stop", "message": {"content": json.dumps(
                    {"summary_ids": [], "topics": [], "uncertainty_ids": []})}}
            return {"done": True, "done_reason": "stop", "message": {"content": json.dumps(
                {"decisions": value["decisions"], "tasks": value["tasks"], "revisions": revisions})}}
        original_fits = llm.fits
        def fits(name, contract, payload, feedback=""):
            return len(payload.get("segments", [])) <= 1 and original_fits(name, contract, payload, feedback)
        with patch.object(llm, "request", side_effect=request) as requests, patch.object(llm, "fits", side_effect=fits):
            with self.assertRaisesRegex(SetupError, "interrupted"):
                worker.document(meeting, refined, llm.models()[1], lambda count: None)
            count = requests.call_count
            document = worker.document(meeting, refined, llm.models()[1], lambda count: None)
            self.assertEqual(requests.call_count, count + 1)
        self.assertEqual(document.record.decisions, [])
        self.assertEqual(reconciliation_inputs[0]["candidates"][0]["fact"]["text"], "We agree to deploy Friday.")
        self.assertEqual(consolidation_inputs[0]["resolved_current"]["decisions"], [])
        self.assertIn("Friday deployment cancelled", [fact.text for fact in document.revision_audit])


if __name__ == "__main__":
    unittest.main()
