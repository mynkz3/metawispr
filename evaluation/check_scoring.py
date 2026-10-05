"""Small scorer check: omissions, duplicate outputs, literal fields and revisions."""
from run import score_document, score_items


def main():
    gold = [{"pattern": "logs", "anchor": "check the logs", "owner": None, "deadline": None}]
    actual = [{"text": "Check the logs", "evidence": [{"quote": "Action item: check the logs."}],
               "owner": None, "deadline": None}]
    assert score_items(actual, gold, fields=True) == {"tp": 1, "fp": 0, "fn": 0, "field_errors": []}
    assert score_items(actual * 2, gold)["fp"] == 1
    assert score_items([], gold)["fn"] == 1
    assert score_items([{**actual[0], "owner": "Sara"}], gold, fields=True)["field_errors"]
    case = {"decisions": [], "tasks": gold, "revision_anchors": ["cancel"]}
    result = {"record": {"decisions": [], "tasks": actual}, "revision_audit": []}
    assert not score_document(result, case)["passed"]
    result["revision_audit"] = [{"evidence": [{"quote": "cancel the old task"}]}]
    assert score_document(result, case)["passed"]
    assert not score_document(None, case)["passed"]
    # Matching must reassign an earlier broad match to preserve a later narrow one.
    expected = [{"pattern": "logs|invoice", "anchor": "action"}, {"pattern": "logs", "anchor": "action"}]
    outputs = [{"text": text, "evidence": [{"quote": "action"}]} for text in ("logs", "invoice")]
    assert score_items(outputs, expected)["tp"] == 2
    print("Scorer checks passed")


if __name__ == "__main__":
    main()
