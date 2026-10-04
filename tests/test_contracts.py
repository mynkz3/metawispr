import unittest

from pydantic import ValidationError

from metawispr.schemas import MeetingRecord, Segment, Task


class ContractTests(unittest.TestCase):
    def test_missing_assignment_details_remain_null(self):
        task = Task.model_validate({
            "text": "Prepare the draft", "owner": None, "deadline": None,
            "evidence": [{"segment_id": "s0001", "quote": "Prepare the draft"}],
        })
        self.assertIsNone(task.owner)
        self.assertIsNone(task.deadline)

    def test_evidence_is_required_for_facts(self):
        with self.assertRaises(ValidationError):
            Task.model_validate({"text": "Invented task", "owner": None, "deadline": None,
                                 "evidence": []})

    def test_empty_decisions_and_tasks_are_valid(self):
        record = MeetingRecord.model_validate({
            "summary": [], "topics": [], "decisions": [], "tasks": [], "uncertainties": [],
        })
        self.assertEqual(record.decisions, [])

    def test_reversed_segment_times_are_rejected(self):
        with self.assertRaises(ValidationError):
            Segment(id="s1", start=5.0, end=2.0, text="Hello")

    def test_unrecognized_model_fields_are_rejected(self):
        with self.assertRaises(ValidationError):
            Segment(id="s1", start=0.0, end=2.0, text="Hello", guessed_speaker="Asha")


if __name__ == "__main__":
    unittest.main()
