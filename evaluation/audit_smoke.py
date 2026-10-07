"""Small authored genuine-Qwen audit probe; this is not an AMI accuracy score."""
from dataclasses import replace
from pathlib import Path
import json

from metawispr.config import Settings
from metawispr.documentation import Documentation, source_units
from metawispr.llm import Ollama, digest, prompt
from metawispr.pipeline import Store
from metawispr.schemas import Fact, MeetingRecord, Segment, Task


def main():
    settings = replace(Settings.from_env(), data_dir=Path(".cache/claim-audit-smoke/data"), llm_timeout_seconds=120)
    store, llm = Store(settings), Ollama(settings)
    meeting = store.begin("authored-component-input.wav", "Authored audit smoke")
    segments = [Segment(id=f"s{i}", start=float(i * 10), end=float((i + 1) * 10), text=text)
                for i, text in enumerate([
                    "Maya will send the report by Friday.",
                    "Perhaps we could add Bluetooth. We have not agreed to do that.",
                    "The target selling price is twenty dollars."])]
    _, sources = source_units(segments)
    record = MeetingRecord(summary=[Fact(text="The profit target is twenty dollars.", evidence=[sources["s2:u000"]])],
                           topics=[], decisions=[], uncertainties=[], tasks=[
                               Task(text="Send the report", owner="Maya", deadline="Friday", evidence=[sources["s0:u000"]]),
                               Task(text="Add Bluetooth", owner=None, deadline=None, evidence=[sources["s1:u000"]])])
    calls, model = [], llm.models()[1]
    try:
        result, withheld, duplicates = Documentation(settings, store, llm).audit(
            meeting, record, sources, model, lambda count: None, calls)
    finally:
        llm.unload(model)
    passed = not result.summary and len(result.tasks) == 1 and result.tasks[0] == record.tasks[0] and withheld == 2
    report = {"scope": "Authored genuine Qwen audit component probe; no ASR or meeting accuracy claim",
              "passed": passed, "withheld": withheld, "duplicates": duplicates,
              "input": {"segments": [item.model_dump() for item in segments], "record": record.model_dump()},
              "output": result.model_dump(), "calls": [call.model_dump() for call in calls],
              "prompt_sha256": digest(prompt("audit"))}
    target = Path(".cache/claim-audit-smoke/result.json")
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"passed": passed, "withheld": withheld, "calls": len(calls), "report": str(target)}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
