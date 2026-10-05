# Shared Qwen 4B deployment

5 October 2026. The owner selected a smaller local deployment: Parakeet v2 INT8
for transcription and one Qwen3.5 4B weight set for both LLM roles. This is a
storage decision, not a claim that 4B passed the real-meeting quality gate.

## Current profile

Both `METAWISPR_REFINER_MODEL` and `METAWISPR_DOCUMENTER_MODEL` now default to
`qwen3.5:4b`. The settings, installed-model adapter and pipeline allow matching
tags or digests. Refinement and documentation still execute sequentially with
different prompts, schemas, source hashes and checkpoint directories. Each call
retains its resolved model digest. Missing models and invalid evidence still fail
explicitly. Stage unload behavior is unchanged; the model is reloaded for the next
role. Custom tags can still select different models.

Setup instructions and the workspace now require only one Qwen download.
Existing completed records retain their original model provenance and remain
readable/exportable. A changed completed-stage policy still cannot silently
overwrite a saved artifact; submit a new recording when changing that policy.

Installed Ollama metadata: `qwen3.5:4b`, reported `4.2B`, `Q4_K_M`, Ollama
`0.35.1`, digest
`d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04`.

The owner's local Qwen 9B was removed with `ollama rm qwen3.5:9b` after the
running application reported 4B for both roles. Granite had already been removed.
Ollama storage decreased from 9,875,013,132 to 3,324,186,459 bytes, freeing
**6,550,826,673 bytes (6.55 GB)**. Parakeet's installed directory is 661,429,406
bytes, making total installed model storage **3,985,615,865 bytes (3.99 GB)**.
These sizes exclude application dependencies, runtime binaries, recordings and
caches, and do not measure RAM or VRAM. Historical comparison outputs were retained.

## Verification

- **74 backend tests passed**, including one installed model serving both roles,
  aliases resolving to the same digest, stage checkpoint separation, retry reuse,
  source/evidence guards and canonical exports. Test doubles identify roles by
  their requested schema, not by assuming different model names.
- `npm run build` passed TypeScript checking and the production Vite build.
- The five fixture browser checks passed, including upload/retry, source review,
  exports, desktop/phone layout and accessibility. The opt-in genuine browser
  upload completed ASR and both shared-model stages, then **failed** its existing
  one-decision assertion: 4B returned the Docker agreement plus the budget fact
  as two decisions. The assertion was retained, not relaxed. The remaining
  assertions in that browser test were not reached; the separate genuine CLI
  verification below checked task fields and ZIP parity. The actual browser-created
  meeting is `30020df9-f9b0-4924-8bce-7b59e31dd8f9` in the API's local data directory.
- CLI `doctor` and the restarted API reported ready with 4B in both role entries
  after removing 9B. There is only one installed Ollama tag.
- A new genuine CLI run processed the authored Windows-voice synthetic sample
  through real FFmpeg preparation, Parakeet CPU INT8, 4B refinement and 4B
  documentation. Meeting `288c5df0-e28a-4e28-96d0-0cab97c411a4` completed. Its
  14.9970625-second input SHA-256 is
  `d5e44fa5d2eaeb68b436a21adf8f85c20f9ecbe8d3cffb97f7a6ec7269ab0c99`.
  Settings: 8,192 context, 2,048 output, temperature/seed zero, thinking disabled,
  two attempts maximum. Both calls used the digest above and completed on their
  first attempts with different prompt/schema hashes and call keys.
- Observed one-run wall time: 44.0 seconds including CLI startup and stage loads.
  ASR load/decode: 4.50/2.92 seconds; refinement/documentation requests: 11.08/23.18
  seconds. These are compatibility observations, not a comparative speed benchmark.
- The sample extracted the Docker agreement and Maya's report task with owner
  `Maya` and relative deadline `Friday`. Raw ASR remained unchanged; the refiner's
  unchanged Docker proposal was rejected as `No change`. Genuine source/provenance
  validation passed. All eight individual export files matched their ZIP entries
  byte-for-byte, and exported JSON matched the canonical record.

**Semantic review did not pass full fidelity:** the CLI record also classified
the budget statement as a decision, although the sample explicitly agreed only
to Docker. Its summary described the budget as "corrected from $50 to $15",
adding a change history not established by the source statement. The same output
correctly retained the absence of an agreement to deploy tomorrow. Exact evidence
checks did not catch the budget interpretation. A completed pipeline and correct
task do not make the entire record accurate.

Local audio, full checkpoints and exports remain ignored in
`.cache/shared-qwen4b/`. The public [AMI evaluation](AMI_ES2002A_EVALUATION.md)
still exposes real-meeting failures; no improved AMI outcome is claimed here.

Reproduce the short compatibility run from the repository root, with the authored
audio described in [PHASE2.md](PHASE2.md), a running Ollama and installed Parakeet:

```powershell
$env:METAWISPR_DATA_DIR = '.cache/shared-qwen4b/data'
.venv/Scripts/python.exe -m metawispr doctor
.venv/Scripts/python.exe -m metawispr process .cache/smoke/meeting.wav --title 'Synthetic shared Qwen 4B compatibility check' --glossary 'Docker'
.venv/Scripts/python.exe -m metawispr export MEETING_UUID --output .cache/shared-qwen4b/exports
```

For the genuine browser test, follow the opt-in instructions in the root README
and use a completed copy of that sample in the running API's data directory.

## Next improvements, without fine-tuning

1. Reserve validation-feedback capacity when forming groups. A repair attempt must
   fit the same source and schema without truncation. Keep context bounded rather
   than compensating with a large unmeasured allocation.
2. Extract assignments, decisions and later revisions before writing narrative
   notes. Use focused schemas/prompts and supporting context for names and roles;
   preserve unstated owners/deadlines as null and relative dates as spoken.
3. Request source segment IDs and exact spans, then construct quotes from those
   selected spans in code. Validate IDs, boundaries and owner/deadline support;
   never substitute fuzzy matches for an unsupported claim. This can avoid quote
   regeneration mistakes, but cannot establish semantic correctness by itself.
4. Strengthen the distinction between stated facts, proposals, agreed decisions
   and past/completed activities. Include short reviewed calibration examples and
   negative cases. A budget fact belongs in notes unless the source establishes
   agreement; a summary must not invent an earlier amount or change history.
5. Reconcile later cancellations/reassignment and check duplicate tasks without
   dropping genuinely different assignments. Retain the existing revision audit.
6. Freeze the revised protocol, retest ES2002a as development data, then evaluate
   separate meeting series and fresh recordings. Measure task/decision precision
   and recall, owner/deadline accuracy, unsupported claims, evidence, latency and
   memory. Passing schemas or exact quotes does not establish coverage or intent.

These changes are planned, not implemented or demonstrated by this deployment
switch. Fine-tuning remains deferred until an improved baseline exposes consistent
errors across reviewed meetings and there are suitable training labels.
