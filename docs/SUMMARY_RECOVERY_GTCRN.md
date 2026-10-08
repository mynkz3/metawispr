# Independent summary recovery and GTCRN, 8 October 2026

The owner requested a useful validated summary even when Qwen cannot produce
some other sections, and requested GTCRN in the application.

## Ordinary inference has no ground-truth transcript

New recording -> normalization and GTCRN -> existing Parakeet v2 INT8 CUDA ->
conservative Qwen3.5 4B terminology refinement -> documentation and claim audit
-> validated record and canonical exports.

The generated transcript supplies evidence for Qwen and validation. Manual
AMI transcripts and reference minutes belong only to evaluation and are never
injected into ordinary inference. Quote/schema matching verifies provenance;
it cannot prove ASR correctness or a claim's interpretation. The same-model
support audit is not an independent accuracy measurement.

## Bounded recovery without accepting invalid claims

Audit prompts explicitly require every candidate ID and short reasons.
When a multi-claim audit still fails its two validation attempts, each claim
gets one independent recovery call (with the existing two-attempt limit).
Singleton failures are withheld; there is no recursive retry loop. Valid
claims remain available and missing audit judgments are never treated as
support. Warnings identify claims withheld because their audits failed.

If action extraction, review or consolidation exhausts model-output validation,
the application generates summary/notes independently from the same refined
transcript. These notes still require valid source references, record validation
and support auditing. A summary with no supported claims remains unpublished.
Runtime/connection errors stay failures rather than being disguised as empty
sections. A failure during the summary-only path also stops publication.

If terminology generation exhausts validation retries, the unchanged raw
segments can continue to documentation with `refinement_available=false`,
no accepted edits and an explicit warning. This records an unavailable
refinement stage without pretending a model successfully corrected anything.

The summary-only record marks tasks and decisions in `unavailable_sections`.
The UI displays a partial-record banner and unavailable section messages;
Markdown and JSON preserve the distinction between unavailable and none stated.
All downloads come from this same validated record. Rejected responses and raw
ASR text remain saved. No manual repairs or ground-truth claims are inserted.

## GTCRN configuration and provenance

`Settings.from_env()` enables GTCRN for new recordings by default. Existing
transcribed meetings reuse their immutable raw checkpoint; restart does not
silently reprocess old transcripts.

```powershell
$env:METAWISPR_USE_GTCRN = '1'
$env:METAWISPR_GTCRN_MODEL = 'models/gtcrn/gtcrn_simple.onnx'
```

The installed official ONNX file is approximately 536 KB and stays outside Git.
Download it from the [sherpa-onnx speech enhancement release](https://github.com/k2-fsa/sherpa-onnx/releases/download/speech-enhancement-models/gtcrn_simple.onnx).
Setting `METAWISPR_USE_GTCRN=0` disables enhancement for new recordings.
Missing weights produce an explicit setup failure, not silent fallback.

GTCRN runs once on CPU before ASR, with no additional recording segmentation.
The original upload and normalized waveform are preserved. Model frame padding
completes the final hop; only added padding is removed from output so every
original frame and recording duration remain represented. Source/model/output
hashes, enhancement timing and padding count are recorded in `enhancement.json`,
raw JSON and final export provenance. Retries verify and reuse enhanced audio.

Enabling GTCRN is the owner's selection, **not a measured WER improvement**.
The earlier full ES2002a experiment regressed from 18.71% to 20.66% aligned WER.
That result and the fixed original-audio baseline remain unchanged. No new
full-meeting accuracy or WER evaluation was performed for this change.

## Verification

- 103 backend tests pass, including broken-refinement/action summary recovery, incomplete
  audit recovery, summary rejection, unavailable export labels, preservation
  of normalized audio, duration and hash-checked enhancement reuse.
- Historical raw/refined/document checkpoints remain readable; a regression
  confirms exact legacy hash acceptance while rejecting changed source text.
- TypeScript and the frontend production build pass.
- Genuine authored compatibility audio completed GTCRN, Parakeet and both Qwen
  roles in 51.01 seconds inside Runner. The independent summary-only path was
  then invoked deliberately; it produced three validated summary points and
  matching ZIP members. This does not simulate an observed real-model action
  failure or measure semantic accuracy. See
  [the genuine compatibility report](../evaluation/results/summary-recovery-smoke.json).
- A real browser check of that generated partial record verifies the banner,
  unavailable task/decision messages and matching JSON export. See
  [browser results](../evaluation/results/summary-recovery-browser.json).
- An initial 0.25-second synthetic PCM check exposed GTCRN's hop-rounded output
  length. It was preserved as a failure report and the padding fix was tested;
  no meeting was repeatedly tuned.

Phase 5 semantic accuracy, independent review and unseen-recording acceptance
remain open. Successful compatibility does not close those gates.
