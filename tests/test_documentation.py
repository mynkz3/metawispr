from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from metawispr.config import Settings, SetupError
from metawispr.documentation import Documentation, apply_edits, validate_record, resolve_candidates, candidate_items, attach_evidence, source_payload, source_units
from metawispr.pipeline import Runner
from metawispr.schemas import DocumentationBatch, Edit, Evidence, Fact, MeetingRecord, ResolvedItem, Resolution, ResolutionBatch, Segment, SourceRecord, Task
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

    def test_context_witness_allows_spelling_but_not_role_completion_or_grammar(self):
        witness = Segment(id="s2", start=10.0, end=20.0, text="We use Docker for deployment.")
        edit = self.edit("dock her", "Docker")
        refined, accepted, _ = apply_edits([self.segment, witness], [edit], "")
        self.assertEqual(accepted, [edit])
        self.assertIn("Docker", refined[0].text)
        self.assertEqual(self.segment.text, "Use dock her, not 50 dollars. Maya will send it by Friday.")
        for original, replacement in [("user interface", "user interface designer"),
                                      ("remote controls", "remote control"), ("GPT4", "GPT5"),
                                      ("Monday", "Tuesday")]:
            segment = Segment(id="x", start=0.0, end=1.0, text=original)
            proposal = Edit(segment_id="x", start=0, end=len(original), original=original,
                            replacement=replacement, reason="Regression fixture")
            self.assertEqual(apply_edits([segment], [proposal], replacement)[1], [])

    def test_quote_and_segment_must_match_exactly(self):
        for evidence in [Evidence(segment_id="missing", quote="Maya"), Evidence(segment_id="s1", quote="maya")]:
            value = record()
            value.decisions.append(Fact(text="fixture", evidence=[evidence]))
            with self.assertRaisesRegex(ValueError, "Evidence"):
                validate_record(value, [self.segment])

    def test_source_selection_constructs_exact_cross_segment_evidence_and_rejects_forgery(self):
        later = Segment(id="s2", start=10.0, end=20.0, text="The report is due Friday.")
        sources = {item.id: Evidence(segment_id=item.id, quote=item.text) for item in [self.segment, later]}
        wire = {"summary": [], "topics": [], "decisions": [], "uncertainties": [], "tasks": [
            {"text": "Send the report", "owner": "Maya", "deadline": "Friday", "evidence_ids": ["s1", "s2"]}]}
        selected = SourceRecord.model_validate(wire)
        expanded = attach_evidence(selected, MeetingRecord, sources)
        validate_record(expanded, [self.segment, later])
        self.assertEqual(expanded.tasks[0].evidence, list(sources.values()))
        payload = source_payload(expanded.model_dump(), sources)
        self.assertEqual(payload["tasks"][0]["evidence_ids"], ["s1", "s2"])
        self.assertEqual(payload["sources"], [{"id": key, "text": value.quote} for key, value in sources.items()])
        for ids in [["missing"], ["s1", "s1"]]:
            wire["tasks"][0]["evidence_ids"] = ids
            with self.assertRaisesRegex(ValueError, "Evidence IDs"):
                attach_evidence(SourceRecord.model_validate(wire), MeetingRecord, sources)
        wire["tasks"][0]["evidence_ids"] = ["s1", "s2"]
        with self.assertRaisesRegex(ValueError, "Evidence IDs"):
            attach_evidence(SourceRecord.model_validate(wire), MeetingRecord, {"s1": sources["s1"]})
        wire["tasks"][0]["quote"] = "Invented quote"
        with self.assertRaises(ValueError):
            SourceRecord.model_validate(wire)

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

    def test_immutable_units_preserve_decimal_text_and_distinguish_repeated_quotes(self):
        segment = Segment(id="s1", start=0.0, end=10.0,
                          text="Filler. " * 450 + "  Budget 12.50 Euro. Maya will send it. Maya will send it.  ")
        units, sources = source_units([segment])
        self.assertEqual(len(units), 453)
        self.assertEqual(units[-3].text, "Budget 12.50 Euro.")
        self.assertEqual(units[-2].text, units[-1].text)
        self.assertNotEqual(sources[units[-2].id].start_char, sources[units[-1].id].start_char)
        self.assertEqual("".join(segment.text.split()),
                         "".join("".join(item.text.split()) for item in units))
        value = record()
        value.summary = [Fact(text="fixture", evidence=[sources[units[-2].id], sources[units[-1].id]])]
        validate_record(value, [segment])
        payload = source_payload(value.model_dump(), sources, include_text=False)
        self.assertEqual(payload["summary"][0]["evidence_ids"], [units[-2].id, units[-1].id])
        self.assertTrue(all("text" not in item for item in payload["sources"]))
        value.summary[0].evidence[0] = value.summary[0].evidence[0].model_copy(update={"end_char": 10000})
        with self.assertRaisesRegex(ValueError, "character range"):
            validate_record(value, [segment])
        value.summary[0].evidence[0] = sources[units[-2].id].model_copy(update={"start_char": 0})
        with self.assertRaisesRegex(ValueError, "character range"):
            validate_record(value, [segment])

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
        _, sources = source_units(segments)
        for batch in (incoming, outgoing):
            for item in [*batch.record.decisions, *batch.revisions]:
                item.evidence = [next(ev for ev in sources.values() if ev.quote == old.quote) for old in item.evidence]
        payload = source_payload({"chronological_batches": [incoming.model_dump(), outgoing.model_dump()]}, sources)
        self.assertEqual(len(payload["sources"]), 2)
        self.assertEqual(payload["chronological_batches"][0]["record"]["decisions"][0]["evidence_ids"], ["s1:u000"])

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
