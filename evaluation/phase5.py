"""Genuine recorded-audio evaluation through the production Runner; no answer injection."""

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from metawispr.audio import file_sha256
from metawispr.config import Settings
from metawispr.documentation import facts, documentation_policy, refinement_policy
from metawispr.exports import export_files
from metawispr.llm import digest, prompt
from metawispr.pipeline import Runner
from metawispr.schemas import RawTranscript
from ami import read, save, GLOSSARY
from run import MeasuredOllama, available_ram


def tokens(text):
    return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)*", text.casefold().replace("\u2019", "'"))


def word_errors(reference, hypothesis):
    # Two DP rows; retain S/D/I counts for one optimal alignment.
    previous = [(j, 0, 0, j) for j in range(len(hypothesis) + 1)]
    for i, word in enumerate(reference, 1):
        current = [(i, 0, i, 0)]
        for j, other in enumerate(hypothesis, 1):
            cost, sub, delete, insert = previous[j - 1]
            diagonal = (cost + (word != other), sub + (word != other), delete, insert)
            cost, sub, delete, insert = previous[j]
            deletion = (cost + 1, sub, delete + 1, insert)
            cost, sub, delete, insert = current[j - 1]
            insertion = (cost + 1, sub, delete, insert + 1)
            current.append(min((diagonal, deletion, insertion), key=lambda item: item[0]))
        previous = current
    errors, sub, delete, insert = previous[-1]
    return {"reference_words": len(reference), "hypothesis_words": len(hypothesis),
            "substitutions": sub, "deletions": delete, "insertions": insert,
            "wer": errors / len(reference) if reference else None}


def aligned_wer(raw, meeting, archive):
    words = []
    with ZipFile(archive) as zipped:
        for name in zipped.namelist():
            if Path(name).name.startswith(meeting + ".") and name.endswith(".words.xml"):
                for word in ET.fromstring(zipped.read(name)):
                    if word.tag == "w" and word.get("punc") != "true" and tokens(word.text or ""):
                        words.append((float(word.get("starttime")), float(word.get("endtime")),
                                      Path(name).name, word.text))
    words.sort(key=lambda item: (item[0], item[2], item[1]))
    first, last = min(word[0] for word in words), max(word[1] for word in words)
    segments = [s for s in raw.segments if s.start >= first and s.end <= last]
    if not segments:
        return {"wer": None, "reason": "No complete ASR window lies inside annotation coverage"}
    start, end = segments[0].start, segments[-1].end
    reference = [token for left, right, _, text in words if start <= (left + right) / 2 < end
                 for token in tokens(text)]
    hypothesis = [token for s in segments for token in tokens(s.text)]
    return {**word_errors(reference, hypothesis), "aligned_start_seconds": start, "aligned_end_seconds": end,
            "excluded_leading_seconds": start, "excluded_trailing_seconds": raw.duration_seconds - end,
            "normalization": "Lowercase; punctuation to separators; apostrophes retained; no number expansion.",
            "alignment": "Complete ASR windows inside lexical annotation coverage; reference words by midpoint. Overlapping speakers sorted by start and speaker file. Not an official AMI benchmark."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=["development", "held-out"], required=True)
    parser.add_argument("--glossary-file", type=Path)
    parser.add_argument("--context", type=int)
    parser.add_argument("--tokens", type=int)
    parser.add_argument("--asr-only", action="store_true", help="Save genuine ASR first; rerun without this flag to resume both LLM stages")
    parser.add_argument("--reuse-asr", type=Path, help="Reuse a verified genuine raw.json and adjacent prepared.wav; report this explicitly")
    parser.add_argument("--resume-report", type=Path, help="Resume an earlier failed run after an explicit configuration fix; save a new report")
    parser.add_argument("--reuse-refined", type=Path, help="Copy a genuine refined.json; production validates its source and current policy before reuse")
    parser.add_argument("--reuse-document-calls", type=Path, help="Genuine saved calls; production identity and validation decide reuse")
    args = parser.parse_args()
    manifest = read(args.root / "manifest.json")
    if manifest["meeting"] != args.meeting:
        parser.error("Meeting ID differs from annotation manifest")
    source = args.root / f"{args.meeting}.Mix-Headset.wav"
    glossary = args.glossary_file.read_text(encoding="utf-8") if args.glossary_file else GLOSSARY
    settings = replace(Settings.from_env(), data_dir=(args.resume_report.parent if args.resume_report else args.output.parent) / "data")
    if args.context is not None:
        settings = replace(settings, llm_context=args.context)
    if args.tokens is not None:
        settings = replace(settings, llm_output_tokens=args.tokens)
    runner = Runner(settings)
    llm = MeasuredOllama(settings, cpu=False)
    runner.llm = llm
    models = llm.models()
    identity = {"meeting": args.meeting, "split": args.split, "input_sha256": file_sha256(source),
                "manual_sha256": file_sha256(args.root / "manual.json"),
                "reference_sha256": file_sha256(args.root / "reference.json"), "glossary": glossary,
                "models": [m.model_dump() for m in models], "context": settings.llm_context,
                "output_tokens": settings.llm_output_tokens,
                "prompts": {name: digest(prompt(name)) for name in ["refine", "document", "review", "notes", "reconcile", "consolidate"]},
                "refinement_policy": refinement_policy(settings, glossary),
                "documentation_policy": documentation_policy(settings)}
    protocol = read(Path(__file__).with_name("phase5-protocol.json"))
    identity["source_sha256"] = {str(path).replace("\\", "/"): file_sha256(path)
                                 for path in sorted([*Path("backend/metawispr").rglob("*.py"),
                                                     *Path("backend/metawispr/prompts").glob("*.txt"),
                                                     Path("evaluation/phase5.py"), Path("evaluation/ami.py"), Path("evaluation/run.py")])}
    entry = next((item for item in protocol["datasets"] if item["meeting"] == args.meeting), None)
    if entry is None or entry["split"] != args.split:
        parser.error("Meeting/split differs from the predeclared Phase 5 protocol")
    for field, actual in [("audio_sha256", identity["input_sha256"]),
                          ("manual_sha256", identity["manual_sha256"]),
                          ("reference_sha256", identity["reference_sha256"])]:
        if entry[field] != actual:
            parser.error(f"Dataset {field} changed since protocol declaration")
    if args.split == "held-out":
        freeze = protocol.get("freeze")
        if not freeze:
            parser.error("Held-out inference requires a frozen pipeline and reviewed references first")
        for field in ("models", "context", "output_tokens", "prompts", "documentation_policy"):
            if freeze[field] != identity[field]:
                parser.error(f"Frozen {field} differs from this run")
        for name, expected in freeze["source_sha256"].items():
            if file_sha256(Path(name)) != expected:
                parser.error(f"Frozen source changed: {name}")
        for name, expected in freeze["gold_sha256"].items():
            if file_sha256(Path(name)) != expected:
                parser.error(f"Reviewed reference changed: {name}")
    if args.output.exists():
        report = read(args.output)
        if report["identity_sha256"] != digest(identity):
            parser.error("Inputs/configuration changed; use a new output path")
        meeting = runner.store.get(report["meeting_id"])
        meeting.target = "transcribed" if args.asr_only else "complete"
        runner.store.put(meeting)
    elif args.resume_report:
        previous_report = read(args.resume_report)
        if previous_report["identity"]["input_sha256"] != identity["input_sha256"] or previous_report["identity"]["meeting"] != args.meeting:
            parser.error("Resume report belongs to another recording")
        meeting = runner.store.get(previous_report["meeting_id"])
        meeting.target = "transcribed" if args.asr_only else "complete"
        runner.store.put(meeting)
        report = {"identity": identity, "identity_sha256": digest(identity), "meeting_id": meeting.id,
                  "dataset": manifest, "host": platform.platform(), "ram_at_start": available_ram(),
                  "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                  "started_at": datetime.now(timezone.utc).isoformat(), "runs": [],
                  "resumed_from": str(args.resume_report),
                  "previous_identity_sha256": previous_report["identity_sha256"],
                  "scope": "Production Runner resumed after an explicit configuration fix. Saved genuine ASR/refinement/calls are reused only when production validation accepts them. This run's wall time excludes prior executions. References excluded from generation."}
        save(args.output, report)
    else:
        meeting = runner.store.begin(source.name, f"AMI {args.meeting}", glossary)
        meeting.target = "transcribed" if args.asr_only else "complete"
        target = runner.store.directory(meeting.id) / meeting.source_name
        shutil.copyfile(source, target)
        meeting.input_sha256, meeting.size_bytes = identity["input_sha256"], target.stat().st_size
        runner.store.put(meeting)
        report = {"identity": identity, "identity_sha256": digest(identity), "meeting_id": meeting.id,
                  "dataset": manifest, "host": platform.platform(), "ram_at_start": available_ram(),
                  "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                  "started_at": datetime.now(timezone.utc).isoformat(), "runs": [],
                  "scope": "Uploaded full AMI audio through genuine Parakeet and both shared-Qwen stages. References excluded from generation. Public corpus pretraining exposure unknown. Semantic grading requires source review."}
        if args.reuse_asr:
            cached = RawTranscript.model_validate(read(args.reuse_asr))
            prepared = args.reuse_asr.parent / "prepared.wav"
            if cached.input_sha256 != identity["input_sha256"] or file_sha256(prepared) != cached.audio_sha256:
                parser.error("Reused ASR source/prepared-audio hashes do not match this recording")
            if cached.model.model_id != "nvidia/parakeet-tdt-0.6b-v2" or cached.model.runtime != "sherpa-onnx" or cached.model.num_threads != settings.asr_threads:
                parser.error("Reused ASR metadata differs from the real configured Parakeet profile")
            if any(file_sha256(settings.model_dir / name) != checksum for name, checksum in cached.model.file_sha256.items()):
                parser.error("Reused ASR weights differ from the installed checkpoint")
            shutil.copyfile(prepared, runner.store.directory(meeting.id) / "prepared.wav")
            runner.store.save_raw(meeting.id, cached)
            report["asr_checkpoint_reused"] = {"path": str(args.reuse_asr), "raw_sha256": file_sha256(args.reuse_asr),
                                               "created_at": cached.created_at,
                                               "note": "No new ASR inference in this execution. Saved genuine decode/load timings are historical; runs.wall_seconds measures this resumed execution only."}
        if args.reuse_refined:
            if not args.reuse_asr:
                parser.error("Refinement reuse requires the verified source ASR checkpoint")
            shutil.copyfile(args.reuse_refined, runner.store.directory(meeting.id) / "refined.json")
            runner.store.refined(meeting.id)
            report["refinement_checkpoint_reused"] = {"path": str(args.reuse_refined),
                                                       "sha256": file_sha256(args.reuse_refined)}
        if args.reuse_document_calls:
            if not args.reuse_asr:
                parser.error("Call reuse requires the verified ASR checkpoint")
            copied = {}
            for saved in args.reuse_document_calls.glob("*.json"):
                destination = runner.store.directory(meeting.id) / "documenting" / "calls" / saved.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(saved, destination)
                copied[saved.name] = file_sha256(saved)
            report["documentation_calls_available_for_reuse"] = {"path": str(args.reuse_document_calls), "sha256": copied,
                "note": "Only exact current production identities passing validation are reused. Saved timings are historical; new API requests are listed under runs.measurements."}
        save(args.output, report)
    put, previous = runner.store.put, [None]
    def progress(state):
        put(state)
        key = (state.stage, state.llm_completed_calls, int(state.processed_audio_seconds // 300))
        if key != previous[0]:
            print(f"{args.meeting}: {state.stage}; {state.processed_audio_seconds:.1f}s audio; {state.llm_completed_calls} saved LLM calls", flush=True)
            previous[0] = key
    runner.store.put = progress
    started = time.perf_counter()
    runner.run(meeting.id)
    state = runner.store.get(meeting.id)
    report["runs"].append({"target": meeting.target, "wall_seconds": time.perf_counter() - started, "measurements": llm.measurements,
                           "stage": state.stage, "error": state.error})
    report["meeting"] = state.model_dump()
    raw = runner.store.raw(meeting.id)
    refined = runner.store.refined(meeting.id)
    document = runner.store.document(meeting.id)
    if raw:
        report["raw"] = raw.model_dump()
        report["asr_word_errors"] = aligned_wer(raw, args.meeting, args.root.parent / "ami_public_manual_1.6.2.zip")
    if refined:
        report["refined"] = refined.model_dump()
    if document:
        report["document"] = document.model_dump()
        outputs = export_files(state, raw, refined, document)
        with ZipFile(BytesIO(outputs["bundle.zip"])) as zipped:
            assert all(zipped.read(name) == body for name, body in outputs.items() if name != "bundle.zip")
        assert json.loads(outputs["meeting.json"])["record"] == document.record.model_dump()
        quote_count = sum(len(fact.evidence) for fact in [*facts(document.record), *document.revision_audit])
        report["structural_checks"] = {"validated_source_references": quote_count,
                                        "zip_members_match": len(outputs) - 1, "canonical_json_matches": True}
        for name in ["meeting.md", "meeting.json", "raw.txt", "refined.txt", "edits.json"]:
            (args.output.parent / name).write_bytes(outputs[name])
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    save(args.output, report)
    print(json.dumps({"meeting": args.meeting, "stage": state.stage, "error": state.error,
                      "output": str(args.output), "wer": report.get("asr_word_errors", {}).get("wer")}), flush=True)
    if state.stage != "complete" and not (args.asr_only and state.stage == "transcribed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
