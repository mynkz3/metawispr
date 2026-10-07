"""Local pretrained extraction and NLI; no training or remote inference."""
from importlib.metadata import version
from pathlib import Path
import gc
import json
import time

from .audio import file_sha256
from .config import SetupError
from .llm import digest


GLINER_MODEL = "fastino/gliner2-base-v1"
NLI_MODEL = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"
THRESHOLD = 0.8  # Provisional support threshold, not a calibrated accuracy probability.
LABELS = ["person", "role", "deadline", "pending work assignment"]


def setup(directory):
    """Explicit network setup only; normal processing loads local snapshots."""
    from huggingface_hub import snapshot_download
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for key, repo in (("gliner", GLINER_MODEL), ("nli", NLI_MODEL)):
        path = Path(snapshot_download(repo, cache_dir=directory / "cache",
                                     allow_patterns=["*.json", "*.safetensors", "*.model", "vocab*", "merges*"]))
        manifest[key] = {"repo": repo, "revision": path.name, "path": str(path.resolve()),
                         "weights_sha256": file_sha256(path / "model.safetensors")}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Hybrid model snapshots saved locally.")


def identity(directory):
    try:
        manifest = json.loads((Path(directory) / "manifest.json").read_text(encoding="utf-8"))
        for key, repo in (("gliner", GLINER_MODEL), ("nli", NLI_MODEL)):
            entry = manifest[key]
            weights = Path(entry["path"]) / "model.safetensors"
            if entry["repo"] != repo or not weights.is_file() or file_sha256(weights) != entry["weights_sha256"]:
                raise ValueError("Missing or incorrect model snapshot")
        return {"models": manifest, "gliner2": version("gliner2"), "transformers": version("transformers"),
                "torch": version("torch"), "threshold": THRESHOLD, "labels": LABELS, "version": 1}
    except (OSError, ValueError, KeyError, ImportError) as exc:
        raise SetupError("Hybrid models are not installed. Install the hybrid extra and run "
                         "python -m metawispr.semantic models/hybrid.") from exc


def dependencies():
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        from gliner2 import GLiNER2
        return torch, AutoModelForSequenceClassification, AutoTokenizer, GLiNER2
    except ImportError as exc:
        raise SetupError("Install Metawispr's hybrid extra before using GLiNER2 and DeBERTa.") from exc


def hints(units, settings, store, meeting_id):
    metadata = identity(settings.hybrid_model_dir)
    key = digest({"identity": metadata, "units": [item.model_dump() for item in units]})
    filename = f"documenting/hybrid/extraction-{key}.json"
    saved = store.read_json(meeting_id, filename)
    if saved is not None:
        return saved["hints"]
    torch, _, _, GLiNER2 = dependencies()
    started = time.perf_counter()
    torch.set_num_threads(4)
    model = GLiNER2.from_pretrained(metadata["models"]["gliner"]["path"], local_files_only=True).eval()
    output = []
    try:
        with torch.inference_mode():
            for unit in units:
                # Source units are short sentences. Never turn encoder truncation
                # into apparent coverage; skip oversized hints, retain all Qwen input.
                if len(model.processor.tokenizer.encode(unit.text)) > 400:
                    continue
                result = model.extract_entities(unit.text, LABELS)
                entities = {label: [text for text in values if isinstance(text, str) and text in unit.text]
                            for label, values in result.get("entities", {}).items()}
                if any(entities.values()):
                    output.append({"source_id": unit.id, "entities": entities})
    finally:
        del model
        gc.collect()
    store.write_json(meeting_id, filename, {"identity": metadata, "hints": output,
                                           "elapsed_seconds": time.perf_counter() - started})
    return output


def score_claims(candidates, settings, store, meeting_id):
    if not candidates:
        return []
    metadata = identity(settings.hybrid_model_dir)
    key = digest({"identity": metadata, "candidates": candidates})
    filename = f"documenting/hybrid/support-{key}.json"
    saved = store.read_json(meeting_id, filename)
    if saved is not None:
        validate_checks(saved["checks"], candidates)
        return saved["checks"]
    torch, AutoModel, AutoTokenizer, _ = dependencies()
    started = time.perf_counter()
    torch.set_num_threads(4)
    path = metadata["models"]["nli"]["path"]
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
    model = AutoModel.from_pretrained(path, local_files_only=True).eval()
    labels = {int(key): value.lower() for key, value in model.config.id2label.items()}
    if set(labels.values()) != {"entailment", "neutral", "contradiction"}:
        raise SetupError("NLI model must expose entailment, neutral and contradiction labels.")
    checks = []
    try:
        with torch.inference_mode():
            for item in candidates:
                fact = item["fact"]
                premise = " ".join(ev["quote"] for ev in fact["evidence"])
                hypothesis = fact["text"]
                if item["topic_title"]:
                    hypothesis = item["topic_title"] + ": " + hypothesis
                if item["kind"] == "task":
                    if fact["owner"]:
                        hypothesis += f" The person or role assigned this task is {fact['owner']}."
                    if fact["deadline"]:
                        hypothesis += f" The deadline for this task is {fact['deadline']}."
                encoded = tokenizer(premise, hypothesis, return_tensors="pt", truncation=False)
                if encoded["input_ids"].shape[1] > 512:
                    scores, verdict = {}, "uncertain"
                else:
                    probabilities = model(**encoded).logits.softmax(-1)[0].tolist()
                    scores = {labels[index]: float(value) for index, value in enumerate(probabilities)}
                    verdict = ("supported" if scores["entailment"] >= THRESHOLD else
                               "unsupported" if scores["contradiction"] >= THRESHOLD else "uncertain")
                checks.append({"candidate_id": item["candidate_id"], "kind": item["kind"], "fact": fact,
                               "verdict": verdict, "scores": scores, "identity": metadata,
                               "reason": "Encoder input exceeds 512 tokens" if not scores else "Pretrained NLI support score"})
    finally:
        del model
        gc.collect()
    store.write_json(meeting_id, filename, {"checks": checks, "elapsed_seconds": time.perf_counter() - started})
    return checks


def validate_checks(checks, candidates):
    by_id = {item["candidate_id"]: item for item in candidates}
    if len(checks) != len(by_id) or {item["candidate_id"] for item in checks} != set(by_id):
        raise SetupError("Saved support checks do not cover the candidate claims exactly once.")
    for check in checks:
        if check["fact"] != by_id[check["candidate_id"]]["fact"]:
            raise SetupError("Saved support check source differs from its original claim.")
        scores = check["scores"]
        if scores and (set(scores) != {"entailment", "neutral", "contradiction"} or
                       not all(isinstance(value, (int, float)) and 0 <= value <= 1 for value in scores.values()) or
                       abs(sum(scores.values()) - 1) > 0.001):
            raise SetupError("Saved support scores are invalid.")
        expected = ("supported" if scores.get("entailment", 0) >= THRESHOLD else
                    "unsupported" if scores.get("contradiction", 0) >= THRESHOLD else "uncertain")
        if check["verdict"] != expected:
            raise SetupError("Saved support verdict differs from its scores.")


if __name__ == "__main__":
    import sys
    setup(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("models/hybrid"))
