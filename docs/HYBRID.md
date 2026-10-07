# Hybrid extraction and support profile

The hybrid profile is explicit (`METAWISPR_HYBRID_ENABLED=1`). The default
remains Qwen-only until model setup succeeds. A missing hybrid dependency or
model fails explicitly when enabled; there is no silent fallback.

## Setup

Install the locked hybrid extra, preserving/reinstalling your matching CUDA
sherpa-onnx wheel when preparing the GPU environment:

```powershell
uv sync --extra hybrid
.\.venv\Scripts\python.exe -m metawispr.semantic models/hybrid
$env:METAWISPR_HYBRID_ENABLED = "1"
```

Initial downloads require network access. Normal inference loads only local
snapshots; meeting audio/text is not sent to Hugging Face. The setup manifest
records snapshot revisions and weight hashes. Weights are excluded from Git.
Encoder inference uses CPU with four threads to reserve GPU memory for
Parakeet and Qwen. This does not switch ASR or Qwen to CPU. Dependencies add
storage beyond the model weights; this is not a free size improvement.

## Ordered workflow

1. Existing immutable Parakeet transcript and guarded Qwen refinement.
2. `fastino/gliner2-base-v1`: source-span hints for people, roles, deadlines
   and pending-work phrases. Original speech is never discarded. Hints are
   untrusted candidates, not assignments. Oversized hint inputs are skipped
   while the complete text still goes to Qwen.
3. Existing fixed Qwen extraction/review/notes/reconciliation and claim audit.
4. `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`: checks each retained whole
   claim against its citations, including task metadata and topic title. A
   provisional 0.8 entailment threshold retains a claim. Other claims are
   withheld; scores are not calibrated correctness probabilities. Encoder
   inputs above 512 tokens become uncertain rather than being truncated.
5. Canonical publication and identical exports. Task ledger events, original
   candidates and NLI scores remain available for inspection.

No prompts or weights are trained/tuned for this integration. No repair loop,
vector database or additional LLM is added. Successful extraction/support
checkpoints are keyed by source/model identity and reused on retry.

## Lifecycle ledger

The ledger records proposed, keep, replace, retire, discard, withheld and
pending events, original task hashes, source evidence and any replacement.
Retirement/replacement uses the existing chronological evidence validation.
A retired task's reason may describe completion or cancellation; code does
not invent that distinction from keywords. Reassignment can be represented
by a replacement task with a different stated owner. The ledger describes
model interpretations; it is not a human-confirmed task management system.

## One-run check

```powershell
.\.venv\Scripts\python.exe evaluation/hybrid_run.py
```

This runs ES2002a once with fixed prompts, isolated data, genuine cached GPU
ASR/refinement and a ten-minute budget on Qwen requests. It preserves partial
checkpoints on failure and does not rerun automatically. It does not download
models during the run. The report explicitly separates prior ASR from new
inference and leaves accuracy ungraded. Support-score counts are not task
precision/recall. Existing meeting records are readable and not overwritten.

Primary model documentation:
- https://huggingface.co/fastino/gliner2-base-v1
- https://huggingface.co/MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli
