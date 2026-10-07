"""Hybrid contract and lifecycle checks; no fabricated accuracy scores."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from metawispr.config import Settings, SetupError
from metawispr.documentation import Documentation, claim_candidates, resolve_candidates, candidate_items
from metawispr.pipeline import Store
from metawispr.schemas import DocumentationBatch, Evidence, MeetingRecord, Resolution, ResolutionBatch, Segment, Task
from metawispr.semantic import validate_checks
from support import FixtureLLM


class HybridTests(unittest.TestCase):
    def test_support_cache_cannot_change_original_claim_or_bypass_threshold(self):
        evidence = Evidence(segment_id="s1", quote="Maya will send it.")
        task = Task(text="Send it", owner="Maya", deadline=None, evidence=[evidence])
        record = MeetingRecord(summary=[], topics=[], decisions=[], tasks=[task], uncertainties=[])
        candidates = claim_candidates(record)
        check = {"candidate_id": "c0000", "fact": task.model_dump(), "verdict": "supported",
                 "scores": {"entailment": 0.9, "neutral": 0.05, "contradiction": 0.05}}
        validate_checks([check], candidates)
        for bad in ([], [check, check], [{**check, "verdict": "uncertain"}],
                    [{**check, "fact": {**task.model_dump(), "owner": "Someone else"}}]):
            with self.assertRaises(SetupError):
                validate_checks(bad, candidates)

    def test_retired_task_has_explicit_later_evidence_in_ledger(self):
        segments = [Segment(id="s1", start=0.0, end=10.0, text="Maya will send it."),
                    Segment(id="s2", start=10.0, end=20.0, text="Cancel sending it.")]
        task = Task(text="Send it", owner="Maya", deadline=None,
                    evidence=[Evidence(segment_id="s1", quote=segments[0].text)])
        record = MeetingRecord(summary=[], topics=[], decisions=[], tasks=[task], uncertainties=[])
        candidates = candidate_items([DocumentationBatch(record=record, revisions=[])])
        later = Evidence(segment_id="s2", quote=segments[1].text)
        output = ResolutionBatch(resolutions=[Resolution(candidate_id=candidates[0]["candidate_id"],
                                 disposition="retire", replacement=None, reason="Explicit cancellation", evidence=[later])])
        ledger = []
        _, tasks, _ = resolve_candidates(output, candidates, segments,
                                        {(item.id, item.text) for item in segments}, ledger)
        self.assertEqual(tasks, [])
        self.assertEqual((ledger[0].event, ledger[0].evidence), ("retire", [later]))

    def test_hybrid_gate_uses_original_facts_and_saves_model_input_hints(self):
        with TemporaryDirectory() as temp:
            settings = Settings(data_dir=Path(temp), hybrid_enabled=True)
            store = Store(settings)
            meeting = store.begin("fixture.wav")
            llm = FixtureLLM(settings)
            unit = Segment(id="s1", start=0.0, end=10.0, text="Maya will send it.")
            refined = type("Input", (), {"segments": [unit], "model_dump": lambda self: {"fixture": True}})()
            worker = Documentation(settings, store, llm)
            with patch("metawispr.semantic.identity", return_value={"test_double": True}), \
                 patch("metawispr.semantic.hints", return_value=[{"source_id": "s1:u000", "entities": {"person": ["Maya"]}}]), \
                 patch("metawispr.semantic.score_claims", side_effect=lambda values, *args: [
                     {"candidate_id": item["candidate_id"], "verdict": "uncertain"} for item in values]):
                result = worker.document(meeting, refined, llm.models()[1], lambda count: None)
            self.assertEqual(result.record.summary, [])
            self.assertEqual(len(result.support_checks), 1)
            import json
            payloads = [json.loads(body["messages"][1]["content"]) for _, body in llm.requests]
            self.assertTrue(any(item.get("extraction_candidates") for item in payloads))


if __name__ == "__main__":
    unittest.main()
