from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from metawispr.config import Settings, SetupError
from metawispr.documentation import Documentation, apply_edits, validate_record, resolve_candidates, candidate_items, consolidation_payload
from metawispr.pipeline import Runner
from metawispr.schemas import DocumentationBatch, Edit, Evidence, Fact, MeetingRecord, ResolvedItem, Resolution, ResolutionBatch, Segment, Task
from support import FixtureASR, FixtureLLM, wav_bytes
from metawispr.audio import file_sha256


def record():
    return MeetingRecord(summary=[], topics=[], decisions=[], tasks=[], uncertainties=[])


class DocumentationTests(unittest.TestCase):
    def setUp(self):
        self.segment = Segment(id="s1", start=0.0, end=10.0,
                               text="Use dock her, not 50 dollars. Maya will send it by Friday.")

    def edit(self, original, replacement, **changes):
        start = self.segment.text.index(original)
        return Edit(segment_id="s1", start=start, end=start + len(original), original=original,
                    replacement=replacement, reason="Explicit test proposal", **changes)

    def test_specific_terminology_edit_preserves_source_and_offsets(self):
        edit = self.edit("dock her", "Docker")
        segments, accepted, rejected = apply_edits([self.segment], [edit], "Docker")
        self.assertEqual(accepted, [edit])
        self.assertEqual(rejected, [])
        self.assertIn("Use Docker, not 50", segments[0].text)
        self.assertIn("dock her", self.segment.text)
        self.assertEqual((segments[0].id, segments[0].start, segments[0].end), ("s1", 0.0, 10.0))

    def test_numbers_negation_and_commitment_changes_are_rejected_even_in_glossary(self):
        edits = [self.edit("50", "15"), self.edit("not", "now"), self.edit("will", "might")]
        _, accepted, rejected = apply_edits([self.segment], edits, "15\nnow\nmight")
        self.assertEqual(accepted, [])
        self.assertEqual(len(rejected), 3)
        self.assertTrue(all("marker" in item.rejection for item in rejected))

    def test_unknown_span_overlap_and_partial_words_are_audited(self):
        good = self.edit("dock her", "Docker")
        unknown = good.model_copy(update={"segment_id": "missing"})
        wrong = good.model_copy(update={"original": "wrong"})
        partial = self.edit("May", "Mayday")
        _, accepted, rejected = apply_edits([self.segment], [unknown, wrong, good, good, partial], "Docker\nMayday")
        self.assertEqual(accepted, [good])
        self.assertEqual(len(rejected), 4)

    def test_unrelated_glossary_replacement_requires_an_explicit_alias(self):
        edit = self.edit("Maya", "API")
        self.assertEqual(len(apply_edits([self.segment], [edit], "API")[2]), 1)
        self.assertEqual(apply_edits([self.segment], [edit], "Maya => API")[1], [edit])

    def test_no_glossary_cannot_rewrite_transcript(self):
        _, accepted, rejected = apply_edits([self.segment], [self.edit("dock her", "Docker")], "")
        self.assertEqual(accepted, [])
        self.assertEqual(len(rejected), 1)

    def test_quote_and_segment_must_match_exactly(self):
        for evidence in [Evidence(segment_id="missing", quote="Maya"), Evidence(segment_id="s1", quote="maya")]:
            value = record()
            value.decisions.append(Fact(text="fixture", evidence=[evidence]))
            with self.assertRaisesRegex(ValueError, "Evidence"):
                validate_record(value, [self.segment])

    def test_owner_and_deadline_must_be_in_supporting_quote(self):
        evidence = [Evidence(segment_id="s1", quote="Maya will send it by Friday.")]
        value = record()
        value.tasks.append(Task(text="Send it", owner="Maya", deadline="Friday", evidence=evidence))
        validate_record(value, [self.segment])
        value.tasks[0].owner = "Alex"
        with self.assertRaisesRegex(ValueError, "owner"):
            validate_record(value, [self.segment])
        value.tasks[0].owner = None
        value.tasks[0].deadline = None
        validate_record(value, [self.segment])

    def test_consolidation_cannot_add_new_evidence(self):
        value = record()
        value.summary.append(Fact(text="fixture", evidence=[Evidence(segment_id="s1", quote="Maya")]))
        with self.assertRaisesRegex(ValueError, "outside"):
            validate_record(value, [self.segment], allowed={("s1", "Use dock her")})

    def test_owner_cannot_be_a_fragment_of_a_different_name(self):
        value = record()
        value.tasks.append(Task(text="Send it", owner="May", deadline=None,
                                evidence=[Evidence(segment_id="s1", quote="Maya will send it by Friday.")]))
        with self.assertRaisesRegex(ValueError, "owner"):
            validate_record(value, [self.segment])

    def test_capacity_failure_does_not_drop_an_oversized_segment(self):
        with TemporaryDirectory() as folder:
            settings = Settings(data_dir=Path(folder))
            runner = Runner(settings)
            meeting = runner.store.begin("a.wav")
            source = runner.store.directory(meeting.id) / meeting.source_name
            source.write_bytes(wav_bytes())
            raw = FixtureASR().transcribe(source, file_sha256(source), "fixture")
            raw.segments[0].text = "x" * 20000
            llm = FixtureLLM(settings)
            with self.assertRaisesRegex(SetupError, "context"):
                Documentation(settings, runner.store, llm).refine(meeting, raw, llm.models()[0], lambda count: None)
            self.assertEqual(llm.requests, [])

    def test_reconciliation_requires_every_candidate_including_unassigned_tasks(self):
        quote = "Action item: check the logs."
        segments = [Segment(id="s1", start=0.0, end=10.0, text=quote)]
        task = Task(text="Check the logs", owner=None, deadline=None,
                    evidence=[Evidence(segment_id="s1", quote=quote)])
        incoming = DocumentationBatch(record=record(), revisions=[])
        incoming.record.tasks = [task]
        candidates = candidate_items([incoming])
        allowed = {("s1", quote)}
        with self.assertRaisesRegex(ValueError, "every candidate"):
            resolve_candidates(ResolutionBatch(resolutions=[]), candidates, segments, allowed)
        resolution = Resolution(candidate_id=candidates[0]["candidate_id"], disposition="keep",
                                replacement=None, evidence=task.evidence, reason="Still active")
        decisions, tasks, revisions = resolve_candidates(ResolutionBatch(resolutions=[resolution]), candidates, segments, allowed)
        self.assertEqual((decisions, tasks, revisions), ([], [task], []))

    def test_retirement_requires_later_evidence_and_preserves_an_audit(self):
        original, cancellation = "We agree to launch Friday.", "Withdraw the Friday launch decision."
        segments = [Segment(id="s1", start=0.0, end=10.0, text=original),
                    Segment(id="s2", start=10.0, end=20.0, text=cancellation)]
        fact = Fact(text="Launch Friday", evidence=[Evidence(segment_id="s1", quote=original)])
        incoming = DocumentationBatch(record=record(), revisions=[])
        incoming.record.decisions = [fact]
        candidates = candidate_items([incoming])
        resolution = Resolution(candidate_id=candidates[0]["candidate_id"], disposition="retire", replacement=None,
                                evidence=fact.evidence, reason="Launch withdrawn")
        allowed = {("s1", original), ("s2", cancellation)}
        with self.assertRaisesRegex(ValueError, "later supporting"):
            resolve_candidates(ResolutionBatch(resolutions=[resolution]), candidates, segments, allowed)
        resolution.evidence = [Evidence(segment_id="s2", quote=cancellation)]
        decisions, tasks, revisions = resolve_candidates(ResolutionBatch(resolutions=[resolution]), candidates, segments, allowed)
        self.assertEqual((decisions, tasks), ([], []))
        self.assertEqual(revisions[0].evidence, [*fact.evidence, *resolution.evidence])
        outgoing = DocumentationBatch(record=record(), revisions=revisions)
        payload = consolidation_payload("Fixture", [incoming, outgoing])
        self.assertEqual(len(payload["evidence"]), 2)
        self.assertEqual(payload["chronological_batches"][0]["record"]["decisions"][0]["evidence_ids"], [0])

    def test_reassignment_requires_a_task_with_quoted_new_owner_and_deadline(self):
        old, new = "Maya will send the report by Friday.", "Alex takes over the report, due Monday."
        segments = [Segment(id="s1", start=0.0, end=10.0, text=old),
                    Segment(id="s2", start=10.0, end=20.0, text=new)]
        original = Task(text="Send the report", owner="Maya", deadline="Friday",
                        evidence=[Evidence(segment_id="s1", quote=old)])
        batch = DocumentationBatch(record=record(), revisions=[])
        batch.record.tasks = [original]
        candidates = candidate_items([batch])
        evidence = [*original.evidence, Evidence(segment_id="s2", quote=new)]
        replacement = ResolvedItem(kind="task", text="Send the report", owner="Invented", deadline="Monday", evidence=evidence)
        resolution = Resolution(candidate_id=candidates[0]["candidate_id"], disposition="replace",
                                replacement=replacement, evidence=evidence, reason="Reassigned and rescheduled")
        result = ResolutionBatch(resolutions=[resolution])
        allowed = {("s1", old), ("s2", new)}
        with self.assertRaisesRegex(ValueError, "owner"):
            resolve_candidates(result, candidates, segments, allowed)
        replacement.owner = "Alex"
        _, tasks, revisions = resolve_candidates(result, candidates, segments, allowed)
        self.assertEqual((tasks[0].owner, tasks[0].deadline), ("Alex", "Monday"))
        self.assertEqual(revisions[0].evidence, evidence)

    def test_unchanged_replacement_has_the_same_effect_as_keep(self):
        quote = "Maya will send the report by Friday."
        segments = [Segment(id="s1", start=0.0, end=10.0, text=quote)]
        task = Task(text=quote, owner="Maya", deadline="Friday", evidence=[Evidence(segment_id="s1", quote=quote)])
        batch = DocumentationBatch(record=record(), revisions=[])
        batch.record.tasks = [task]
        candidates = candidate_items([batch])
        replacement = ResolvedItem(kind="task", **task.model_dump())
        result = ResolutionBatch(resolutions=[Resolution(candidate_id=candidates[0]["candidate_id"], disposition="replace",
                                  replacement=replacement, evidence=task.evidence, reason="Same stated action")])
        self.assertEqual(resolve_candidates(result, candidates, segments, {("s1", quote)}), ([], [task], []))

    def test_explicit_reclassification_preserves_assignment_evidence(self):
        quote = "Maya will send the report by Friday."
        segments = [Segment(id="s1", start=0.0, end=10.0, text=quote)]
        fact = Fact(text=quote, evidence=[Evidence(segment_id="s1", quote=quote)])
        batch = DocumentationBatch(record=record(), revisions=[])
        batch.record.decisions = [fact]
        candidates = candidate_items([batch])
        replacement = ResolvedItem(kind="task", text=quote, owner="Maya", deadline="Friday", evidence=fact.evidence)
        result = ResolutionBatch(resolutions=[Resolution(candidate_id=candidates[0]["candidate_id"], disposition="replace",
                                  replacement=replacement, evidence=fact.evidence, reason="Commitment belongs in tasks")])
        decisions, tasks, audit = resolve_candidates(result, candidates, segments, {("s1", quote)})
        self.assertEqual(decisions, [])
        self.assertEqual(tasks[0].owner, "Maya")
        self.assertEqual(audit[0].evidence, fact.evidence)


if __name__ == "__main__":
    unittest.main()
