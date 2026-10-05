"""Real local LLM component evaluation; no fake ASR or LLM judge.

Run from the repository root with its installed Python environment. Reuses the
production prompts, schemas, guards and grouping functions. The production
Runner's distinct-weight policy is deliberately unchanged by this experiment.
"""

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import re
import statistics
import subprocess
import time
from types import SimpleNamespace

from metawispr.config import Settings, SetupError
from metawispr.documentation import Documentation, groups
from metawispr.llm import Ollama, digest, prompt
from metawispr.pipeline import Store, atomic_write
from metawispr.schemas import SourceBatch, LLMModel, Segment


def segments(texts):
    return [Segment(id=f"s{i + 1:05d}", start=float(i * 30), end=float((i + 1) * 30), text=text)
            for i, text in enumerate(texts)]


def authored_input(items, origin):
    # Component input deliberately carries no invented recording or ASR metadata.
    return SimpleNamespace(segments=items, model_dump=lambda: {
        "origin": origin, "segments": [item.model_dump() for item in items]})


def matches(actual, expected):
    return (re.search(expected["pattern"], actual["text"], re.IGNORECASE) is not None
            and any(expected["anchor"] in evidence["quote"] for evidence in actual["evidence"]))


def score_items(actual, expected, fields=False):
    # Maximum matching counts each expected item and output once, including duplicates.
    assigned = {}

    def assign(gold, visited):
        for index, item in enumerate(actual):
            if index in visited or not matches(item, expected[gold]):
                continue
            visited.add(index)
            if index not in assigned or assign(assigned[index], visited):
                assigned[index] = gold
                return True
        return False

    for gold in range(len(expected)):
        assign(gold, set())
    errors = []
    if fields:
        for index, gold in assigned.items():
            for field in ("owner", "deadline"):
                if actual[index][field] != expected[gold][field]:
                    errors.append({"item": index, "field": field, "actual": actual[index][field],
                                   "expected": expected[gold][field]})
    return {"tp": len(assigned), "fp": len(actual) - len(assigned),
            "fn": len(expected) - len(assigned), "field_errors": errors}


def score_document(result, case):
    record = result["record"] if result else {"decisions": [], "tasks": []}
    decisions = score_items(record["decisions"], case["decisions"])
    tasks = score_items(record["tasks"], case["tasks"], fields=True)
    revisions = result["revision_audit"] if result else []
    missing = [anchor for anchor in case.get("revision_anchors", [])
               if not any(anchor in evidence["quote"] for revision in revisions
                          for evidence in revision["evidence"])]
    return {"decisions": decisions, "tasks": tasks, "missing_revision_anchors": missing,
            "passed": bool(result) and not missing and all(
                score["fp"] == score["fn"] == 0 and not score["field_errors"]
                for score in (decisions, tasks))}


def expand_case(case, llm):
    case = dict(case)
    if case.get("force_two_groups"):
        payload = lambda items: {"title": case["id"], "segments": [item.model_dump() for item in items]}
        for count in range(1, 150):
            items = segments([text + " The team reviewed background context." * count for text in case["texts"]])
            batches = groups(items, payload, lambda value: llm.fits("document", SourceBatch, value))
            if len(batches) == 2:
                case["texts"] = [item.text for item in items]
                case["filler_repetitions"] = count
                break
        else:
            raise ValueError("Cannot construct the fixed two-group probe within this context")
    return case


def available_ram():
    if platform.system() != "Windows":
        return None
    import ctypes
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    *[(name, ctypes.c_ulonglong) for name in
                      ("total", "available", "page_total", "page_available", "virtual_total",
                       "virtual_available", "extended_available")]]
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return {"total_bytes": status.total, "available_bytes": status.available}


class MeasuredOllama(Ollama):
    def __init__(self, settings, cpu):
        super().__init__(settings)
        self.cpu, self.measurements = cpu, []

    def request(self, method, path, body=None, timeout=None):
        if path != "/api/chat":
            return super().request(method, path, body, timeout)
        if self.cpu:
            body = {**body, "options": {**body["options"], "num_gpu": 0}}
        observation = {"model": body["model"], "options": body["options"], "ram_before": available_ram()}
        started = time.perf_counter()
        try:
            response = super().request(method, path, body, timeout)
            observation.update({name: response.get(name) for name in
                                ("done_reason", "total_duration", "load_duration", "prompt_eval_count",
                                 "prompt_eval_duration", "eval_count", "eval_duration")})
            return response
        except SetupError as exc:
            observation["error"] = str(exc)
            raise
        finally:
            observation["wall_seconds"] = time.perf_counter() - started
            observation["ram_after"] = available_ram()
            try:
                observation["resident_models"] = super().request("GET", "/api/ps", timeout=3).get("models", [])
            except SetupError as exc:
                observation["memory_error"] = str(exc)
            self.measurements.append(observation)


def model_metadata(llm, tag):
    installed = llm.request("GET", "/api/tags", timeout=3)["models"]
    entry = next((item for item in installed if item["name"] == tag), None)
    if entry is None:
        raise SetupError(f"Install the selected model first: ollama pull {tag}")
    details = entry["details"]
    return LLMModel(tag=tag, digest=entry["digest"], runtime_version=llm.request("GET", "/api/version")["version"],
                    parameter_size=details["parameter_size"], quantization=details["quantization_level"]), entry["size"]


def summarize(jobs):
    result = {}
    for role in ("refinement", "documentation"):
        subset = [job for job in jobs if job["role"] == role and job["status"] != "pending"]
        completed = [job for job in subset if job["status"] == "complete"]
        result[role] = {"cases": len(subset), "validated": len(completed),
                        "passed": sum(job["score"]["passed"] for job in subset),
                        "median_case_wall_seconds": statistics.median(job["wall_seconds"] for job in subset) if subset else None,
                        "attempts": sum(len(job["measurements"]) for job in subset)}
        if role == "documentation":
            for kind in ("decisions", "tasks"):
                totals = {key: sum(job["score"][kind][key] for job in subset) for key in ("tp", "fp", "fn")}
                totals["precision"] = totals["tp"] / (totals["tp"] + totals["fp"]) if totals["tp"] + totals["fp"] else None
                totals["recall"] = totals["tp"] / (totals["tp"] + totals["fn"]) if totals["tp"] + totals["fn"] else None
                result[role][kind] = totals
            result[role]["task_field_errors"] = sum(len(job["score"]["tasks"]["field_errors"]) for job in subset)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cpu", action="store_true", help="Force zero GPU layers; uses an isolated output directory")
    parser.add_argument("--cases", nargs="*", help="Optional case IDs for a clearly separate subset run")
    args = parser.parse_args()
    settings = replace(Settings.from_env(), data_dir=args.output.parent / "checkpoints", llm_timeout_seconds=600)
    llm = MeasuredOllama(settings, args.cpu)
    model, size = model_metadata(llm, args.model)
    corpus = json.loads(Path(__file__).with_name("cases.json").read_text(encoding="utf-8"))
    cases = [(role, expand_case(case, llm)) for role in ("refinement", "documentation")
             for case in corpus[role] if args.cases is None or case["id"] in args.cases]
    if args.cases and set(args.cases) != {case["id"] for _, case in cases}:
        parser.error("Unknown or empty case selection")
    if not cases:
        parser.error("No cases selected")
    identity = {"model": model.model_dump(), "cpu": args.cpu, "context": settings.llm_context,
                "output_tokens": settings.llm_output_tokens, "cases": cases,
                "prompt_sha256": {name: digest(prompt(name)) for name in ("refine", "document", "reconcile", "consolidate")}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        report = json.loads(args.output.read_text(encoding="utf-8"))
        if report["identity_sha256"] != digest(identity):
            raise ValueError("Output belongs to different cases, settings, prompts or weights; use a new path")
    else:
        report = {"identity_sha256": digest(identity), "identity": identity, "model_package_bytes": size,
                  "started_at": datetime.now(timezone.utc).isoformat(), "host": platform.platform(),
                  "logical_cpus": __import__("os").cpu_count(), "ram_at_start": available_ram(),
                  "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                  "scope": corpus["description"], "jobs": []}
    store = Store(settings)
    for role, case in cases:
        job = next((job for job in report["jobs"] if job["role"] == role and job["id"] == case["id"]), None)
        if job and job["status"] != "pending":
            print(f"Saved {args.model} {role}/{case['id']}: {job['status']}", flush=True)
            continue
        # Each component gets correct role-specific policy metadata. The unused
        # configured role remains distinct; the real Runner is not exercised here.
        other = "qwen3.5:9b" if args.model != "qwen3.5:9b" else "qwen3.5:4b"
        role_settings = replace(settings, refiner_model=args.model if role == "refinement" else other,
                                documenter_model=args.model if role == "documentation" else other)
        worker = Documentation(role_settings, store, llm)
        if job is None:
            meeting = store.begin("authored-component-input.wav", case["id"], case.get("glossary", ""))
            job = {"role": role, "id": case["id"], "meeting_id": meeting.id, "status": "pending"}
            report["jobs"].append(job)
            atomic_write(args.output, json.dumps(report, indent=2))
        else:
            meeting = store.get(job["meeting_id"])
        items = segments(case["texts"])
        source = authored_input(items, "hand-authored raw" if role == "refinement" else "hand-authored reference refined")
        llm.measurements = []
        llm.unload(model)
        started = time.perf_counter()
        print(f"Running {args.model} {'CPU' if args.cpu else 'default offload'} {role}/{case['id']}", flush=True)
        try:
            method = worker.refine if role == "refinement" else worker.document
            output = method(meeting, source, model, lambda count: print(f"  validated call {count}", flush=True))
            result = output.model_dump()
            job.update(status="complete", output=result)
            job["score"] = ({"passed": [item.text for item in output.segments] == case["expected_texts"],
                             "accepted": len(output.accepted), "rejected": len(output.rejected)}
                            if role == "refinement" else score_document(result, case))
        except (SetupError, ValueError) as exc:
            job.update(status="failed", error=str(exc))
            job["score"] = ({"passed": False, "accepted": 0, "rejected": 0} if role == "refinement"
                            else score_document(None, case))
        job.update(wall_seconds=time.perf_counter() - started, measurements=llm.measurements)
        report["summary"] = summarize(report["jobs"])
        atomic_write(args.output, json.dumps(report, ensure_ascii=False, indent=2))
        print(f"  {job['status']}; assertions passed={job['score']['passed']}; {job['wall_seconds']:.1f}s", flush=True)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    atomic_write(args.output, json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
