"""Compute metrics from an explicit source review, never from an LLM judge."""
import argparse
import json
from pathlib import Path

from metawispr.audio import file_sha256


def score(report, gold, review):
    record = report.get("document", {}).get("record", {})
    result = {"meeting": gold["meeting"], "review_status": review["review_status"],
              "pipeline_complete": report["meeting"]["stage"] == "complete", "metrics": {}}
    for kind in ("tasks", "decisions"):
        predictions, labels = record.get(kind, []), review[kind]
        if [item["index"] for item in labels] != list(range(len(predictions))):
            raise ValueError(f"Review must cover every {kind} prediction once in index order")
        gold_ids = {item["id"] for item in gold[kind]}
        matched = set()
        correct = 0
        for label in labels:
            ids = set(label["matched_gold_ids"])
            if not ids <= gold_ids or not label["rationale"]:
                raise ValueError("Unknown gold ID or missing source-review rationale")
            if ids and label["source_supported"] and not ids <= matched:
                correct += 1
                matched.update(ids)
        result["metrics"][kind] = {"predictions": len(predictions), "gold_atoms": len(gold_ids),
                                  "correct_predictions": correct, "matched_atoms": len(matched),
                                  "precision": correct / len(predictions) if predictions else None,
                                  "recall": len(matched) / len(gold_ids) if gold_ids else None,
                                  "missed_gold_ids": sorted(gold_ids - matched)}
    tasks = review["tasks"]
    result["metrics"]["task_metadata"] = {
        "owner_correct": sum(item["owner_correct"] for item in tasks),
        "deadline_correct": sum(item["deadline_correct"] for item in tasks),
        "predictions": len(tasks),
        "invented_owners": sum(item["invented_owner"] for item in tasks),
        "invented_deadlines": sum(item["invented_deadline"] for item in tasks)}
    fact_paths = [f"summary/{i}" for i in range(len(record.get("summary", [])))]
    fact_paths += [f"topics/{i}/{j}" for i, topic in enumerate(record.get("topics", [])) for j in range(len(topic["points"]))]
    if [item["path"] for item in review["notes"]] != fact_paths:
        raise ValueError("Review must cover every summary/topic point in display order")
    result["metrics"]["notes"] = {"facts": len(fact_paths),
                                  "unsupported": sum(not item["source_supported"] for item in review["notes"])}
    if len(review["key_topic_coverage"]) != len(gold["key_topics"]):
        raise ValueError("Review every predeclared key topic")
    result["metrics"]["key_topics"] = {"covered": sum(item["covered"] for item in review["key_topic_coverage"]),
                                       "expected": len(gold["key_topics"])}
    checks = report.get("structural_checks", {})
    result["exports_consistent"] = checks.get("zip_members_match") == 8 and checks.get("canonical_json_matches") is True
    result["source_reference_count"] = checks.get("validated_source_references", 0)
    quality = result["pipeline_complete"] and result["exports_consistent"]
    for kind in ("tasks", "decisions"):
        metrics = result["metrics"][kind]
        quality &= (metrics["precision"] is None and not metrics["gold_atoms"] or (metrics["precision"] or 0) >= .95)
        quality &= not metrics["gold_atoms"] or (metrics["recall"] or 0) >= .90
    quality &= not result["metrics"]["notes"]["unsupported"]
    quality &= not any(item["invented_owner"] or item["invented_deadline"] for item in tasks)
    quality &= all(item["owner_correct"] and item["deadline_correct"] for item in tasks)
    result["engineering_quality_gate_passed"] = bool(quality)
    result["release_verified"] = False  # independent human/audio review is still required
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("report", "gold", "review", "output"):
        parser.add_argument(f"--{field}", type=Path, required=True)
    args = parser.parse_args()
    report, gold, review = [json.loads(path.read_text(encoding="utf-8")) for path in (args.report, args.gold, args.review)]
    if report["identity"]["meeting"] != gold["meeting"] or review["meeting"] != gold["meeting"]:
        parser.error("Report, gold and review belong to different meetings")
    if review["report_sha256"] != file_sha256(args.report) or review["gold_sha256"] != file_sha256(args.gold):
        parser.error("Review does not match these exact artifacts")
    result = score(report, gold, review)
    result["artifact_sha256"] = {name: file_sha256(getattr(args, name)) for name in ("report", "gold", "review")}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
