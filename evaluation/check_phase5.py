"""Small independent examples checking WER counts and normalization."""
from phase5 import tokens, word_errors
from grade_phase5 import score

assert tokens("We CAN'T pay $12.50!") == ["we", "can't", "pay", "12", "50"]
for ref, hyp, counts in [
    ([], [], (0, 0, 0)),
    (["a"], [], (0, 1, 0)),
    ([], ["a"], (0, 0, 1)),
    (["a"], ["b"], (1, 0, 0)),
    (["a", "b", "c", "d"], ["a", "x", "c", "e", "f"], (2, 0, 1)),
]:
    result = word_errors(ref, hyp)
    assert (result["substitutions"], result["deletions"], result["insertions"]) == counts, result
assert word_errors([], ["a"])["wer"] is None
print("PASS: known substitution/deletion/insertion alignments; normalization; N/A empty reference")

gold = {"meeting": "authored metric check", "tasks": [{"id": "a"}, {"id": "b"}], "decisions": [], "key_topics": []}
report = {"meeting": {"stage": "complete"}, "document": {"record": {"tasks": [{}], "decisions": [], "summary": [], "topics": []}},
          "structural_checks": {"zip_members_match": 8, "canonical_json_matches": True}}
label = {"index": 0, "matched_gold_ids": ["a", "b"], "source_supported": True, "rationale": "Authored compound prediction covers both atoms",
         "owner_correct": True, "deadline_correct": True, "invented_owner": False, "invented_deadline": False}
review = {"review_status": "Authored metric check only", "tasks": [label], "decisions": [], "notes": [], "key_topic_coverage": []}
result = score(report, gold, review)
assert result["metrics"]["tasks"]["precision"] == 1 and result["metrics"]["tasks"]["recall"] == 1
label["matched_gold_ids"] = ["a"]
assert score(report, gold, review)["metrics"]["tasks"]["recall"] == .5
report["document"]["record"]["tasks"].append({})
review["tasks"].append({**label, "index": 1})
assert score(report, gold, review)["metrics"]["tasks"]["precision"] == .5  # duplicate is not a second true positive
report["meeting"]["stage"] = "failed"
assert not score(report, gold, review)["engineering_quality_gate_passed"]
print("PASS: compound atomic recall; duplicate precision; N/A decisions; failed run cannot pass")
