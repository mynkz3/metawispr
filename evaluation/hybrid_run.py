"""One fixed-prompt hybrid ES2002a run, reusing genuine GPU ASR/refinement."""
from dataclasses import replace
from pathlib import Path
from collections import Counter
import json
import shutil
import time

from metawispr.config import Settings, SetupError
from metawispr.documentation import facts
from metawispr.exports import export_files
from metawispr.llm import Ollama, digest, prompt
from metawispr.pipeline import Runner


class BudgetOllama(Ollama):
    def __init__(self, settings, deadline):
        super().__init__(settings)
        self.deadline = deadline

    def request(self, method, path, body=None, timeout=None):
        remaining = self.deadline - time.perf_counter()
        if remaining <= 0:
            raise SetupError("Single-run ten-minute inference budget reached; checkpoints retained. No automatic rerun.")
        return super().request(method, path, body, min(timeout or self.settings.llm_timeout_seconds, remaining))


def main():
    baseline_path = Path(".cache/phase5/gpu-int8-es2002a/final-profile/results.json")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    source = baseline_path.parent / "data" / baseline["meeting_id"]
    settings = replace(Settings.from_env(), data_dir=Path(".cache/hybrid-es2002a/data"), hybrid_enabled=True)
    runner = Runner(settings)
    original = json.loads((source / "meeting.json").read_text(encoding="utf-8"))
    meeting = runner.store.begin("ES2002a.wav", "AMI ES2002a hybrid fixed-prompt run", original["glossary"])
    target = runner.store.directory(meeting.id)
    for name in ("prepared.wav", "raw.json", "refined.json"):
        shutil.copy2(source / name, target / name)
    shutil.copy2(source / original["source_name"], target / meeting.source_name)
    meeting.input_sha256 = original["input_sha256"]
    meeting.size_bytes = original["size_bytes"]
    runner.store.put(meeting)
    before_prompts = {name: digest(prompt(name)) for name in
                      ("refine", "document", "review", "notes", "reconcile", "consolidate", "audit")}
    started = time.perf_counter()
    runner.llm = BudgetOllama(settings, started + 600)
    runner.run(meeting.id)
    wall = time.perf_counter() - started
    state = runner.store.get(meeting.id)
    document = runner.store.document(meeting.id)
    report = {"scope": "Single development meeting, fixed prompts, genuine Qwen/GLiNER2/DeBERTa. Saved genuine CUDA ASR and refinement reused; no new WER measurement.",
              "baseline_report": str(baseline_path), "baseline_sha256": digest(baseline),
              "prompt_sha256": before_prompts, "meeting_id": meeting.id,
              "wall_seconds": wall, "stage": state.stage, "error": state.error,
              "baseline_tasks": len(baseline["document"]["record"]["tasks"]),
              "accuracy_status": "Not independently graded; model support scores are not precision or recall."}
    if document:
        report["document"] = document.model_dump()
        report["stats"] = {"tasks": len(document.record.tasks), "decisions": len(document.record.decisions),
                           "note_facts": len(document.record.summary) + sum(len(topic.points) for topic in document.record.topics),
                           "qwen_calls": len(document.calls),
                           "nli_verdicts": dict(Counter(item["verdict"] for item in document.support_checks)),
                           "task_events": dict(Counter(item.event for item in document.task_ledger))}
        refined = runner.store.refined(meeting.id)
        files = export_files(state, runner.store.raw(meeting.id), refined, document)
        for name, content in files.items():
            (target / name).write_bytes(content)
        report["exports_match_canonical_record"] = json.loads(files["meeting.json"])["record"] == document.record.model_dump()
    report["hybrid_checkpoints"] = [json.loads(path.read_text(encoding="utf-8"))
                                   for path in (target / "documenting/hybrid").glob("*.json")]
    output = Path("evaluation/results/hybrid-es2002a.json")
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("stage", "wall_seconds", "error")}, indent=2))
    if document:
        print(json.dumps(report["stats"], indent=2))
    return 0 if state.stage == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
