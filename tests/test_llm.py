from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

import httpx

from metawispr.config import Settings, SetupError
from metawispr.llm import Ollama
from metawispr.pipeline import Store
from metawispr.schemas import EditBatch
from support import FixtureLLM


class LLMTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.settings = Settings(data_dir=Path(self.folder.name))
        self.store = Store(self.settings)
        self.meeting = self.store.begin("a.wav")
        self.llm = FixtureLLM(self.settings)
        self.model = self.llm.models()[0]

    def generate(self, payload=None):
        return self.llm.generate(self.model, "refine", EditBatch, payload or {"segments": []}, self.store,
                                 self.meeting.id, "refining", lambda result: None)

    def test_successful_call_is_reused_with_exact_identity(self):
        first = self.generate()
        second = self.generate()
        self.assertEqual(first, second)
        self.assertEqual(len(self.llm.requests), 1)
        body = self.llm.requests[0][1]
        self.assertFalse(body["stream"])
        self.assertFalse(body["think"])
        self.assertEqual(body["options"]["temperature"], 0)
        self.assertEqual(body["options"]["presence_penalty"], 0)
        self.assertEqual(body["options"]["repeat_penalty"], 1)
        self.assertEqual(body["format"], EditBatch.model_json_schema())
        self.generate({"segments": ["different input"]})
        self.assertEqual(len(self.llm.requests), 2)

    def test_invalid_json_gets_one_bounded_retry(self):
        real_request = self.llm.request
        attempts = []
        def request(*args, **kwargs):
            attempts.append(args)
            if len(attempts) == 1:
                return {"done": True, "done_reason": "stop", "message": {"content": "not JSON"}}
            return real_request(*args, **kwargs)
        with patch.object(self.llm, "request", side_effect=request):
            _, call = self.generate()
        self.assertEqual(call.attempts, 2)
        self.assertEqual(len(attempts), 2)
        self.assertIn("failed validation", attempts[1][2]["messages"][-1]["content"])

    def test_truncated_outputs_are_never_saved(self):
        with patch.object(self.llm, "request", return_value={"done": True, "done_reason": "length",
                                                            "message": {"content": '{"edits":[]}'}}) as request:
            with self.assertRaisesRegex(SetupError, "twice"):
                self.generate()
        self.assertEqual(request.call_count, 2)
        self.assertEqual(list(self.store.directory(self.meeting.id).glob("refining/calls/*.json")), [])

    def test_changed_digest_does_not_reuse_old_calls(self):
        self.generate()
        self.model = self.model.model_copy(update={"digest": "c" * 64})
        self.generate()
        self.assertEqual(len(self.llm.requests), 2)

    def test_bad_cached_output_fails_instead_of_bypassing_validation(self):
        self.generate()
        path = next(self.store.directory(self.meeting.id).glob("refining/calls/*.json"))
        saved = json.loads(path.read_text())
        saved["output"] = {"unexpected": True}
        path.write_text(json.dumps(saved))
        with self.assertRaisesRegex(SetupError, "saved LLM call"):
            self.generate()

    def test_missing_and_same_weight_models_are_explicit_errors(self):
        llm = Ollama(self.settings)
        with patch.object(llm, "request", return_value={"models": [], "version": "fixture"}):
            with self.assertRaisesRegex(SetupError, "missing"):
                llm.models()
        tags = {"models": [{"name": tag, "digest": "a" * 64, "details": {}} for tag in
                            (self.settings.refiner_model, self.settings.documenter_model)]}
        with patch.object(llm, "request", side_effect=[tags, {"version": "fixture"}]):
            with self.assertRaisesRegex(SetupError, "same weights"):
                llm.models()

    def test_network_failure_is_actionable(self):
        with patch("metawispr.llm.httpx.Client") as client:
            client.return_value.__enter__.return_value.request.side_effect = httpx.ConnectError("fixture")
            with self.assertRaisesRegex(SetupError, "Local Ollama"):
                Ollama(self.settings).models()
            self.assertFalse(client.call_args.kwargs["trust_env"])

    def test_remote_endpoint_and_identical_tags_are_rejected(self):
        for changes in ({"ollama_url": "https://example.com"}, {"documenter_model": "qwen3.5:4b"}):
            with self.assertRaises(ValueError):
                Settings(**changes)


if __name__ == "__main__":
    unittest.main()
