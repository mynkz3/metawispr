"""Genuine no-glossary refinement on saved AMI ASR; not a full-pipeline run."""
import argparse
from dataclasses import replace
from pathlib import Path
import time

from metawispr.audio import file_sha256
from metawispr.config import Settings
from metawispr.documentation import Documentation
from metawispr.llm import digest, prompt
from metawispr.pipeline import Store
from metawispr.schemas import RawTranscript
from ami import read, save
from run import MeasuredOllama


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True, help="Saved genuine glossary refinement")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw_hash = file_sha256(args.raw)
    raw = RawTranscript.model_validate(read(args.raw))
    baseline = read(args.baseline)
    if baseline["source_sha256"] != digest(raw.model_dump()):
        parser.error("Glossary baseline belongs to a different ASR transcript")
    settings = replace(Settings.from_env(), data_dir=args.output.parent / "data")
    store, llm = Store(settings), MeasuredOllama(settings, cpu=False)
    meeting = store.begin(f"{args.meeting}.wav", f"AMI {args.meeting}", "")
    model = llm.models()[0]
    started = time.perf_counter()
    result = Documentation(settings, store, llm).refine(meeting, raw, model, lambda count: print(f"{args.meeting}: {count} genuine refinement calls", flush=True))
    save(args.output, {"meeting": args.meeting, "scope": __doc__, "glossary": "", "input_raw_sha256": file_sha256(args.raw),
                       "baseline_sha256": file_sha256(args.baseline), "raw_before_after_equal": raw_hash == file_sha256(args.raw),
                       "prompt_sha256": digest(prompt("refine")), "model": model.model_dump(),
                       "wall_seconds": time.perf_counter() - started, "measurements": llm.measurements,
                       "with_glossary": {"accepted": baseline["accepted"], "rejected": baseline["rejected"]},
                       "without_glossary": result.model_dump(),
                       "quality_note": "Accepted count is not correction precision. Review genuine errors separately from cosmetic edits and already-correct text; no human/audio adjudication claimed."})
    print(f"Saved {args.output}", flush=True)


if __name__ == "__main__":
    main()
