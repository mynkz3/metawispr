# Delivery verification, 8 October 2026

## Frozen delivery configuration

Original recorded English audio -> Parakeet v2 INT8 on CUDA -> Qwen3.5 4B
terminology refinement -> Qwen3.5 4B documentation -> source/schema validation
-> canonical exports. Raw transcription and edit history remain separate.
One Qwen weight set serves two ordered stages; no fine-tuning is performed.
GTCRN is not enabled: its full ES2002a comparison increased aligned WER from
18.71% to 20.66%. No new enhancement model, dependency or prompt change is
part of this delivery check.

The active development meetings are ES2002a and IS1000b. Both have already
been inspected; neither is an unseen or blind test. Preserve the historical
[ES2002a baseline](BASELINE.md), including its measurement interval and
provisional documentation scores. Do not claim the current documentation
policy has been tested on both recordings from scratch.

## Checks completed

- Backend: 96 unittest checks pass, including stage recovery, source
  validation, invalid-input handling and canonical exports.
- Frontend: TypeScript check and production Vite build pass.
- Evaluation: known WER alignments/normalization and scoring edge cases pass.
- Dependency lock: `uv --cache-dir .cache/uv lock --check --offline` passes
  (25 packages). The first attempt could not write uv's default external
  cache; the workspace cache avoided that permission issue. This does not
  verify a clean dependency installation or replace the CUDA runtime setup.
- Playwright: five fixture browser checks pass, covering upload/polling,
  desktop review, failure/retry, phone layout and accessibility. The opt-in
  model-backed synthetic upload test was skipped.
- Readiness: local FFmpeg conversion, Parakeet CUDA INT8 weights/runtime and
  Qwen3.5 4B are reported ready. This check is not a new ASR inference.

The Windows readiness command was run with existing native-library folders
on the process PATH: `D:\Lib\site-packages\torch\lib` and
`.cache/ollama-runtime/lib/ollama/cuda_v12`. This machine-specific setup is
not a portable clean-install verification.

## Second-meeting execution

One IS1000b execution uses the current application Runner, models and prompts,
reusing its genuine, hash/profile-verified original-audio CUDA INT8 transcript.
No new ASR inference or timing is claimed. Historical aligned WER is 22.91%
over 228.0-2283.2 seconds; the recording lasts 2343.7 seconds.

Run report: `.cache/delivery-is1000b/results.json`. Exact identities, policy
hashes, source hashes, measurements and failures are preserved there. The
recording and runtime checkpoints remain outside Git. A completed record
does not establish semantic accuracy; documentation must be compared with
the predeclared references before assigning precision or recall.

The [frozen profile](../evaluation/delivery-profile.json) records the model,
prompt and source identities used for this execution. The working tree had
pre-existing evaluation/documentation changes; source hashes identify the
actual run more precisely than its Git HEAD alone.

Reproduction from the repository root, after supplying the two-meeting AMI
cache and native runtime setup:

```powershell
.venv/Scripts/python.exe evaluation/phase5.py --meeting IS1000b --root .cache/ami/is1000b --split development --output .cache/delivery-is1000b/results.json --reuse-asr .cache/phase5/gpu-int8-is1000b/final-profile/data/4cf97002-8c09-40be-872e-e5e2ac002cdc/raw.json
```

The command resumes matching checkpoints when its output already exists.
Use a new output directory for a deliberate fresh execution; do not overwrite
historical results to make a failed condition disappear.

### Actual outcome

**The current IS1000b execution failed during the final claim audit.** Qwen
omitted required candidate verdicts on both attempts; validation rejected
them with `Audit every candidate_id exactly once`. The rejected responses
are preserved as [attempt 1](../evaluation/results/delivery-audit-rejected-1.json)
and [attempt 2](../evaluation/results/delivery-audit-rejected-2.json).
No new prompt or configuration change, manual verdict repair or rerun followed.

The [execution report](../evaluation/results/delivery-is1000b.json) records
586.33 seconds (9 minutes 46 seconds) inside Runner, excluding the reused ASR
and subsequent WER scoring. It contains 57 new request measurements, four
completed refinement calls, five accepted edits and 44 rejected proposals.
The failed meeting state reports 50 completed documentation calls. Accepted
edits are guard-approved, not independently verified corrections.

There is no validated final document, so current-run task precision/recall,
decision accuracy and summary faithfulness are **unscored**. The saved
22.91% ASR WER is unchanged. Successful intermediate calls do not make the
pipeline complete.

The [real browser check](../evaluation/results/delivery-browser-check.json)
confirms the failure state, visible retry control, preserved raw/refined
transcripts and absence of page errors. No retry was clicked. The
[HTTP export check](../evaluation/results/delivery-export-check.json) confirms
that both available transcript downloads match their canonical segments;
incomplete Markdown/ZIP exports correctly return 409. Separately, the saved
historical completed IS1000b record passes current HTTP ZIP/member byte parity
and canonical JSON record matching. That is compatibility evidence for an
older record, not completion or accuracy evidence for this run.

The concrete remaining reliability issue is incomplete final-audit responses
blocking an otherwise checkpointed record. Any future recovery must preserve
coverage and evidence validation; silently accepting missing verdicts would
remove the intended guard. No such change is included here.

AMI-derived transcripts and responses in the reports retain AMI attribution;
source recordings, model weights and caches are not committed.

## Acceptance limits

Phase 5 remains open for documentation accuracy, terminology-positive coverage,
independent audio/reference adjudication and a genuinely unseen recording.
The existing implementation and compatibility checks do not justify marking
those gates complete. This verification is a bounded delivery pass, not a
model or prompt search.
