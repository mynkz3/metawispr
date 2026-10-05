"""Revalidate saved genuine AMI artifacts and matched model-comparison inputs."""

import argparse
from collections import defaultdict

from ami import GLOSSARY, read, source_input
from metawispr.documentation import apply_edits, validate_record
from metawispr.llm import digest
from metawispr.schemas import DocumentedMeeting, RawTranscript, RefinedTranscript


def main():
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(".cache/ami/es2002a"))
    args = parser.parse_args()
    manual = read(args.root / "manual.json")
    raw_value = read(args.root / "raw.json")
    raw = RawTranscript.model_validate(raw_value)
    manifest = read(args.root / "manifest.json")
    assert digest(manual) == manifest["manual_input_sha256"]
    assert digest(raw_value) == manifest["asr_input_sha256"]
    assert digest(read(args.root / "reference.json")) == manifest["reference_sha256"]
    conditions = defaultdict(list)
    completed = failed = requests = 0
    for path in sorted(args.root.glob("*k/results.json")):
        report = read(path)
        identity = report["identity"]
        assert report.get("finished_at"), f"Unfinished report: {path}"
        assert digest(identity) == report["identity_sha256"]
        assert identity["manual_input_sha256"] == digest(manual)
        assert identity["asr_input_sha256"] == digest(raw_value)
        assert identity["reference_sha256"] == manifest["reference_sha256"]
        conditions[identity["context"], identity["output_tokens"]].append(identity)
        assert {j["role"] for j in report["jobs"]} == {"manual-documentation", "asr-refinement", "asr-documentation"}
        refined = None
        for job in report["jobs"]:
            requests += len(job.get("measurements", []))
            if job["status"] in {"failed", "skipped"}:
                assert "output" not in job and job.get("error")
                failed += 1
                continue
            assert job["status"] == "complete"
            if job["role"] == "asr-refinement":
                refined = RefinedTranscript.model_validate(job["output"])
                assert refined.source_sha256 == digest(raw_value)
                replay, accepted, rejected = apply_edits(raw.segments, refined.accepted, GLOSSARY)
                assert not rejected and accepted == refined.accepted and replay == refined.segments
                output = refined
            else:
                output = DocumentedMeeting.model_validate(job["output"])
                source = source_input(manual) if job["role"] == "manual-documentation" else refined
                assert source is not None
                assert output.source_sha256 == digest(source.model_dump())
                validate_record(output.record, source.segments, output.revision_audit)
            for call in output.calls:
                assert call.model.model_dump() == identity["model"]
                assert call.context == identity["context"] and call.output_tokens == identity["output_tokens"]
                assert call.temperature == call.seed == 0 and call.thinking is False
            completed += 1
    expected = {"qwen3.5:4b", "qwen3.5:9b", "metawispr-granite4-h-micro:q4_k_m"}
    assert conditions, "No completed comparison reports"
    for profiles in conditions.values():
        assert {p["model"]["tag"] for p in profiles} == expected and len(profiles) == 3
        assert len({digest({k: v for k, v in p.items() if k != "model"}) for p in profiles}) == 1
    print(f"Verified {len(conditions)} matched conditions; {completed} completed, {failed} failed/skipped jobs; {requests} genuine requests")


if __name__ == "__main__":
    main()
