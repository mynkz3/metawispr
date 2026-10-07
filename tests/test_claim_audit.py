"""Contract checks, not measurements of model accuracy."""
import unittest

from metawispr.documentation import claim_candidates, publish_supported, source_payload, source_units, validate_claim_audit
from metawispr.schemas import ClaimAudit, ClaimVerdict, Fact, MeetingRecord, Segment, Topic


class ClaimAuditTests(unittest.TestCase):
    def test_complete_judgments_and_original_evidence_are_required_before_filtering(self):
        segments = [Segment(id="s1", start=0.0, end=10.0, text="Maya will send the report.")]
        _, sources = source_units(segments)
        fact = Fact(text="Maya will send the report", evidence=list(sources.values()))
        record = MeetingRecord(summary=[fact, fact], topics=[Topic(title="Unsupported title", points=[fact])],
                               decisions=[], tasks=[], uncertainties=[])
        candidates = source_payload({"candidates": claim_candidates(record)}, sources)["candidates"]
        verdicts = [ClaimVerdict(candidate_id=item["candidate_id"], verdict="supported" if index < 2 else "uncertain",
                                 evidence_ids=item["fact"]["evidence_ids"], reason="Explicit test verdict")
                    for index, item in enumerate(candidates)]
        validate_claim_audit(ClaimAudit(verdicts=verdicts), candidates)
        for bad in (verdicts[:-1], [verdicts[0], verdicts[0], verdicts[2]],
                    [verdicts[0].model_copy(update={"evidence_ids": ["other"]}), *verdicts[1:]]):
            with self.assertRaises(ValueError):
                validate_claim_audit(ClaimAudit(verdicts=bad), candidates)
        result, duplicates = publish_supported(record, {"c0000", "c0001"})
        self.assertEqual((result.summary, result.topics, duplicates), ([fact], [], 1))
        self.assertEqual(len(record.summary), 2)
        self.assertEqual(result.summary[0].evidence, fact.evidence)


if __name__ == "__main__":
    unittest.main()
