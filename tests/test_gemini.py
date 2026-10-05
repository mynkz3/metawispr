"""Synthetic HTTP contracts only; these checks do not measure Gemini accuracy."""

from dataclasses import replace
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from metawispr.config import Settings, SetupError
from metawispr.documentation import documentation_policy, refinement_policy
from metawispr.llm import Gemini, Ollama, llm_client, llm_readiness
from metawispr.pipeline import Runner, Store
from metawispr.schemas import EditBatch
from support import FixtureASR, FixtureLLM, wav_bytes


class GeminiTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.settings = Settings(data_dir=Path(self.folder.name), llm_backend="gemini",
                                 refiner_model="gemini-3.8-flash", documenter_model="gemini-3.8-flash")
        self.store = Store(self.settings)
        self.meeting = self.store.begin("fixture.wav")
        self.llm = Gemini(self.settings)
        self.requests = []
        self.replies = []
        self.environment = patch.dict(os.environ, {"GEMINI_API_KEY": "synthetic-key"}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        client = httpx.Client
        self.real_client = client
        self.transport = patch("metawispr.llm.httpx.Client", side_effect=lambda **kw: client(
            transport=httpx.MockTransport(self.respond), **kw))
        self.client_mock = self.transport.start()
        self.addCleanup(self.transport.stop)

    def respond(self, request):
        self.requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"name": "models/gemini-3.8-flash", "version": "fixture-version",
                                          "supportedGenerationMethods": ["generateContent"],
                                          "inputTokenLimit": 1048576, "outputTokenLimit": 65536})
        if self.replies:
            return self.replies.pop(0)
        return httpx.Response(200, json={"modelVersion": "fixture-response-version",
            "candidates": [{"finishReason": "STOP", "content": {"parts": [
                {"text": "hidden reasoning", "thought": True}, {"text": '{"edits":[]}'}]}}],
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 6, "thoughtsTokenCount": 12}})

    def generate(self, validate=lambda output: None):
        return self.llm.generate(self.llm.models()[0], "refine", EditBatch,
                                 {"segments": [{"id": "s1", "text": "Send 15 reports."}]},
                                 self.store, self.meeting.id, "refining", validate)

    def test_default_environment_selects_gemini_and_explicit_qwen_remains_available(self):
        settings = Settings.from_env()
        self.assertIsInstance(llm_client(settings), Gemini)
        self.assertEqual(settings.refiner_model, "gemini-3.8-flash")
        with patch.dict(os.environ, {"METAWISPR_LLM_BACKEND": "ollama"}):
            self.assertIsInstance(llm_client(Settings.from_env()), Ollama)
            self.assertEqual(Settings.from_env().refiner_model, "qwen3.5:4b")
        with self.assertRaises(ValueError):
            replace(self.settings, refiner_model="../other-endpoint")

    def test_wire_auth_schema_usage_provenance_and_checkpoint_reuse(self):
        models = self.llm.models()
        self.assertEqual(models[0], models[1])
        self.assertEqual(len(self.requests), 1)
        self.assertTrue(models[0].digest.startswith("metadata_sha256:"))
        first = self.generate()
        self.assertEqual(first, self.generate())
        posts = [r for r in self.requests if r.method == "POST"]
        self.assertEqual(len(posts), 1)
        request = posts[0]
        self.assertEqual(request.headers["x-goog-api-key"], "synthetic-key")
        self.assertEqual(request.url.query, b"")
        config = json.loads(request.content)["generationConfig"]
        self.assertEqual(config["responseJsonSchema"]["$defs"]["EditProposal"]["properties"]["segment_id"]["enum"], ["s1"])
        self.assertEqual(config["thinkingConfig"]["thinkingLevel"], "LOW")
        self.assertNotIn("num_gpu", config)
        self.assertTrue(first[1].thinking)
        self.assertEqual(first[1].thought_tokens, 12)
        self.assertEqual(first[1].response_model_version, "fixture-response-version")
        self.assertIsNone(first[1].repeat_penalty)
        self.assertNotIn("synthetic-key", next(self.store.directory(self.meeting.id).glob("refining/calls/*.json")).read_text())

    def test_invalid_or_truncated_output_uses_bounded_retry_and_preserves_failure(self):
        self.replies = [httpx.Response(200, json={"candidates": [{"finishReason": "MAX_TOKENS",
                       "content": {"parts": [{"text": '{"edits":[]}'}]}}]})]
        _, call = self.generate()
        self.assertEqual(call.attempts, 2)
        posts = [json.loads(r.content) for r in self.requests if r.method == "POST"]
        self.assertEqual(posts[0]["contents"][0]["parts"][0], posts[1]["contents"][0]["parts"][0])
        self.assertIn("failed validation", posts[1]["contents"][0]["parts"][-1]["text"])
        self.assertEqual(len(list(self.store.directory(self.meeting.id).glob("refining/failed/*.json"))), 1)

    def test_blocked_responses_never_become_successful_empty_records(self):
        self.replies = [httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}) for _ in range(2)]
        with self.assertRaisesRegex(SetupError, "twice"):
            self.generate()
        self.assertEqual(list(self.store.directory(self.meeting.id).glob("refining/calls/*.json")), [])

    def test_quota_and_auth_errors_are_redacted_and_no_fallback_occurs(self):
        self.replies = [httpx.Response(429, json={"error": {"message": "synthetic-key private transcript"}})]
        with self.assertRaisesRegex(SetupError, "429.*Quota") as error:
            self.generate()
        self.assertNotIn("synthetic-key", str(error.exception))
        self.assertEqual(len([r for r in self.requests if r.method == "POST"]), 1)
        with patch.dict(os.environ, {}, clear=True):
            report = llm_readiness(self.settings)
            self.assertFalse(report["llm_ready"])
            self.assertEqual(report["transcript_processing"], "google_api")
            self.assertIn("GEMINI_API_KEY", report["llm_error"])

    def test_semantic_validator_still_rejects_response_and_cached_output(self):
        with self.assertRaisesRegex(SetupError, "twice"):
            self.generate(lambda output: (_ for _ in ()).throw(ValueError("Unsupported correction")))
        self.generate()
        with self.assertRaisesRegex(SetupError, "saved LLM call"):
            self.generate(lambda output: (_ for _ in ()).throw(ValueError("Unsupported correction")))

    def test_provider_policies_differ_and_pipeline_uses_gemini_for_both_stages(self):
        local = replace(self.settings, llm_backend="ollama")
        self.assertNotEqual(refinement_policy(local, ""), refinement_policy(self.settings, ""))
        self.assertNotEqual(documentation_policy(local), documentation_policy(self.settings))
        runner = Runner(self.settings)
        self.assertIsInstance(runner.llm, Gemini)
        runner.asr = FixtureASR()
        fixture = FixtureLLM(self.settings)
        def respond(request):
            if request.method == "GET":
                return self.respond(request)
            body = json.loads(request.content)
            response = fixture.request("POST", "/api/chat", {"format": body["generationConfig"]["responseJsonSchema"],
                "messages": [{"content": body["systemInstruction"]["parts"][0]["text"]},
                             {"content": body["contents"][0]["parts"][0]["text"]}]})
            return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {
                "parts": [{"text": response["message"]["content"]}]}}]})
        meeting = runner.store.begin("fixture.wav")
        directory = runner.store.directory(meeting.id)
        audio = wav_bytes()
        (directory / meeting.source_name).write_bytes(audio)
        from hashlib import sha256
        meeting.input_sha256, meeting.size_bytes = sha256(audio).hexdigest(), len(audio)
        runner.store.put(meeting)
        self.client_mock.side_effect = lambda **kw: self.real_client(transport=httpx.MockTransport(respond), **kw)
        runner.run(meeting.id)
        self.assertEqual(runner.store.get(meeting.id).stage, "complete")
        self.assertEqual(runner.store.refined(meeting.id).calls[0].model.tag, "gemini-3.8-flash")
        self.assertIsNone(runner.store.refined(meeting.id).calls[0].prompt_tokens)
        self.assertTrue(all(call.thinking for call in runner.store.document(meeting.id).calls))


if __name__ == "__main__":
    unittest.main()
