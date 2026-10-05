"""Evaluate a public AMI meeting with genuine local production components.

Download the official manual-annotation ZIP and mixed-headset WAV first; see README.
Reference summaries are retained for review and never included in model requests.
"""

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import re
import subprocess
import time
from types import SimpleNamespace
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from metawispr.audio import Parakeet, file_sha256, prepare_audio
from metawispr.config import Settings, SetupError
from metawispr.documentation import Documentation, groups
from metawispr.llm import digest, prompt
from metawispr.pipeline import Store, atomic_write
from metawispr.schemas import SourceBatch, Segment, RawTranscript
from run import MeasuredOllama, available_ram, model_metadata


NITE = "{http://nite.sourceforge.net/}"
MEETING = "ES2002a"
ANNOTATIONS_URL = "https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/ami_public_manual_1.6.2.zip"
AUDIO_URL = "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/ES2002a/audio/ES2002a.Mix-Headset.wav"
# Scenario vocabulary chosen before inspecting ASR/model output; no correction aliases.
GLOSSARY = "Real Reaction\nremote control\nindustrial designer\nuser interface designer\nmarketing executive\nproject manager\nLCD\ninfrared"


def save(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def referenced(href, trees):
    match = re.fullmatch(r"([^#]+)#id\(([^)]+)\)(?:\.\.id\(([^)]+)\))?", href)
    if match is None:
        raise ValueError(f"Unsupported NXT reference: {href}")
    filename, first, last = match.groups()
    elements = [item for item in trees[filename].iter() if item.get(NITE + "id")]
    positions = {item.get(NITE + "id"): index for index, item in enumerate(elements)}
    start, end = positions[first], positions[last or first]
    if end < start:
        raise ValueError("NXT reference range is reversed")
    return elements[start:end + 1]


def words_for(element, trees):
    return [word for child in element.findall(NITE + "child")
            for word in referenced(child.attrib["href"], trees) if word.tag == "w"]


def render_words(words):
    # Preserve case, disfluencies, contractions and lexical tokens; attach punctuation.
    return re.sub(r"\s+([,.;:!?])", r"\1", " ".join((item.text or "") for item in words)).strip()


def prepare(root):
    archive = root.parent / "ami_public_manual_1.6.2.zip"
    with ZipFile(archive) as zipped:
        selected = {name: zipped.read(name) for name in zipped.namelist()
                    if MEETING in Path(name).name and name.endswith(".xml")}
    trees = {Path(name).name: ET.fromstring(data) for name, data in selected.items()}
    segments, mapping, covered = [], [], []
    for speaker in "ABCD":
        for element in trees[f"{MEETING}.{speaker}.segments.xml"]:
            words = words_for(element, trees)
            text = render_words(words)
            if not text:
                continue
            item = {"start": float(element.attrib["transcriber_start"]),
                    "end": float(element.attrib["transcriber_end"]), "text": text,
                    "speaker": speaker, "annotation_id": element.get(NITE + "id"),
                    "word_ids": [word.get(NITE + "id") for word in words]}
            segments.append(item)
            covered.extend(item["word_ids"])
    expected = [word.get(NITE + "id") for speaker in "ABCD"
                for word in trees[f"{MEETING}.{speaker}.words.xml"] if word.tag == "w"]
    if len(covered) != len(set(covered)) or set(covered) != set(expected):
        raise ValueError("Manual transcript lost or duplicated annotated word tokens")
    segments.sort(key=lambda item: (item["start"], item["speaker"], item["end"]))
    for index, item in enumerate(segments, 1):
        identifier = f"m{index:04d}"
        mapping.append({"id": identifier, **item})
    items = [Segment(id=item["id"], start=item["start"], end=item["end"], text=item["text"])
             for item in mapping]
    transcript = {"origin": "AMI manual orthographic transcription v1.6.2; no ASR inference",
                  "meeting": MEETING, "speaker_labels_in_model_text": False,
                  "segments": [item.model_dump() for item in items]}
    reference = {section.tag: [{"id": sentence.get(NITE + "id"), "text": sentence.text.strip()}
                              for sentence in section.findall("sentence")]
                 for section in trees[f"{MEETING}.abssumm.xml"]}
    links = []
    for element in trees[f"{MEETING}.summlink.xml"]:
        pointers = {item.get("role"): item.get("href") for item in element.findall(NITE + "pointer")}
        utterances = referenced(pointers["extractive"], trees)
        words = [word for utterance in utterances for word in words_for(utterance, trees)]
        links.append({"summary_ids": [item.get(NITE + "id") for item in referenced(pointers["abstractive"], trees)],
                      "text": render_words(words), "word_ids": [item.get(NITE + "id") for item in words]})
    reference["source_links"] = links
    reference["decision_spans"] = [{"id": item.get(NITE + "id"), "external": item.get("external"),
                                     "text": render_words(words_for(item, trees))}
                                    for item in trees[f"{MEETING}.decision.xml"]]
    manifest = {"meeting": MEETING, "prepared_at": datetime.now(timezone.utc).isoformat(),
                "source": "AMI Meeting Corpus, Edinburgh/Idiap/TNO; AMI Project",
                "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "dataset_url": "https://groups.inf.ed.ac.uk/ami/corpus/",
                "annotations_url": ANNOTATIONS_URL, "annotations_sha256": file_sha256(archive),
                "audio_url": AUDIO_URL, "annotation_file_sha256": {name: sha256(data).hexdigest()
                                                                      for name, data in selected.items()},
                "manual_segments": len(items), "lexical_tokens_with_punctuation": len(expected),
                "manual_input_sha256": digest(transcript), "reference_sha256": digest(reference),
                "glossary": GLOSSARY, "speaker_prefixes_added": False,
                "manual_timestamp_note": "Original annotation segment times; overlapping speaker turns are retained.",
                "reference_note": "Official abstract/actions/decisions/problems plus linked evidence; excluded from all model prompts."}
    save(root / "manual.json", transcript)
    save(root / "manual-source-map.json", mapping)
    save(root / "reference.json", reference)
    save(root / "manifest.json", manifest)
    atomic_write(root / "manual.txt", "\n".join(f"{s.id} [{s.start:.2f}-{s.end:.2f}] {s.text}" for s in items) + "\n")
    print(json.dumps({key: manifest[key] for key in ("meeting", "manual_segments", "lexical_tokens_with_punctuation",
                                                     "manual_input_sha256", "reference_sha256")}), flush=True)


def transcribe(root):
    manifest = read(root / "manifest.json")
    source = root / f"{MEETING}.Mix-Headset.wav"
    input_hash = file_sha256(source)
    if (root / "raw.json").exists():
        raw = RawTranscript.model_validate(read(root / "raw.json"))
        if raw.input_sha256 != input_hash:
            raise ValueError("Saved ASR belongs to different audio")
        print("Reusing saved genuine ASR", flush=True)
        return
    settings = Settings.from_env()
    started = time.perf_counter()
    duration = prepare_audio(source, root / "prepared.wav", settings)
    asr = Parakeet(settings)
    raw = asr.transcribe(root / "prepared.wav", input_hash, datetime.now(timezone.utc).isoformat(),
                         lambda end: print(f"ASR {end:.1f}/{duration:.1f} seconds", flush=True))
    save(root / "raw.json", raw.model_dump())
    atomic_write(root / "raw.txt", "\n".join(s.text for s in raw.segments) + "\n")
    manifest.update(audio_sha256=input_hash, duration_seconds=duration,
                    asr_wall_seconds=time.perf_counter() - started, asr_input_sha256=digest(raw.model_dump()))
    save(root / "manifest.json", manifest)
    print(json.dumps({"duration_seconds": duration, "asr_segments": len(raw.segments),
                      "asr_wall_seconds": manifest["asr_wall_seconds"]}), flush=True)


def source_input(value):
    return SimpleNamespace(segments=[Segment.model_validate(item) for item in value["segments"]],
                           model_dump=lambda: value)


def run(args):
    settings = replace(Settings.from_env(), data_dir=args.output.parent / "checkpoints",
                       llm_context=args.context, llm_output_tokens=args.tokens, llm_timeout_seconds=900)
    llm = MeasuredOllama(settings, False)
    model, size = model_metadata(llm, args.model)
    manual = read(args.root / "manual.json")
    raw = read(args.root / "raw.json")
    manifest = read(args.root / "manifest.json")
    if digest(manual) != manifest["manual_input_sha256"] or digest(read(args.root / "reference.json")) != manifest["reference_sha256"]:
        raise ValueError("Prepared manual input/reference changed after manifest creation")
    identity = {"model": model.model_dump(), "context": args.context, "output_tokens": args.tokens,
                "manual_input_sha256": digest(manual), "asr_input_sha256": digest(raw),
                "glossary": GLOSSARY, "reference_sha256": manifest["reference_sha256"],
                "rubric_sha256": file_sha256(Path(__file__).with_name("ami-es2002a-rubric.json")),
                "prompts": {name: digest(prompt(name)) for name in ("refine", "document", "reconcile", "consolidate")}}
    if args.output.exists():
        report = read(args.output)
        if report["identity_sha256"] != digest(identity):
            raise ValueError("Changed inputs/settings/weights: use a new output path")
    else:
        report = {"identity": identity, "identity_sha256": digest(identity), "dataset": manifest,
                  "model_package_bytes": size, "ram_at_start": available_ram(),
                  "host": platform.platform(), "logical_cpus": __import__("os").cpu_count(),
                  "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                  "started_at": datetime.now(timezone.utc).isoformat(), "jobs": [],
                  "scope": "One public AMI meeting; manual-documentation and shared-weight ASR/refinement/documentation component arms. Production Runner policy unchanged."}
    store = Store(settings)
    for role, input_value in (("manual-documentation", manual), ("asr-refinement", raw), ("asr-documentation", None)):
        job = next((item for item in report["jobs"] if item["role"] == role), None)
        if job and job["status"] != "pending":
            print(f"Saved {args.model} {role}: {job['status']}", flush=True)
            continue
        if role == "asr-documentation":
            refinement = next(item for item in report["jobs"] if item["role"] == "asr-refinement")
            if refinement["status"] != "complete":
                report["jobs"].append({"role": role, "status": "skipped", "error": "Refinement failed"})
                save(args.output, report)
                continue
            input_value = refinement["output"]
        if job is None:
            meeting = store.begin(f"{MEETING}.Mix-Headset.wav", f"AMI {MEETING}", GLOSSARY)
            job = {"role": role, "meeting_id": meeting.id, "status": "pending"}
            report["jobs"].append(job)
            save(args.output, report)
        else:
            meeting = store.get(job["meeting_id"])
        other = "qwen3.5:9b" if args.model != "qwen3.5:9b" else "qwen3.5:4b"
        role_settings = replace(settings, refiner_model=args.model if role == "asr-refinement" else other,
                                documenter_model=other if role == "asr-refinement" else args.model)
        worker = Documentation(role_settings, store, llm)
        source = source_input(input_value)
        job["input_sha256"] = digest(input_value)
        if role != "asr-refinement":
            payload = lambda items: {"title": meeting.title, "segments": [item.model_dump() for item in items]}
            job["initial_groups"] = len(groups(source.segments, payload, lambda value: llm.fits("document", SourceBatch, value)))
        llm.measurements = []
        llm.unload(model)
        started = time.perf_counter()
        print(f"Running {args.model} {role} context={args.context} output={args.tokens}", flush=True)
        try:
            method = worker.refine if role == "asr-refinement" else worker.document
            output = method(meeting, source, model, lambda count: print(f"  validated call {count}", flush=True))
            job.update(status="complete", output=output.model_dump())
        except (SetupError, ValueError) as exc:
            job.update(status="failed", error=str(exc))
        job.update(wall_seconds=time.perf_counter() - started, measurements=llm.measurements)
        # Preserve every attempted response, including responses rejected by production guards.
        job["rejected_responses"] = [read(path) for path in sorted(store.directory(meeting.id).glob("*/failed/*.json"))]
        save(args.output, report)
        print(f"  {job['status']}; {job['wall_seconds']:.1f}s; {len(llm.measurements)} requests", flush=True)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    save(args.output, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "asr", "run"])
    parser.add_argument("--root", type=Path, default=Path(".cache/ami/es2002a"))
    parser.add_argument("--model")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--context", type=int, default=32768)
    parser.add_argument("--tokens", type=int, default=4096)
    args = parser.parse_args()
    if args.command == "run" and (not args.model or args.output is None):
        parser.error("run requires --model and --output")
    {"prepare": lambda: prepare(args.root), "asr": lambda: transcribe(args.root), "run": lambda: run(args)}[args.command]()


if __name__ == "__main__":
    main()
