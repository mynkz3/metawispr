# Phase 5 implementation and verification

Follow [WORKPLAN.md](WORKPLAN.md). This log records implemented changes and actual
runs, including failures; it is not a declaration that Phase 5 is complete.

## 5.1 Retry capacity, 5 October 2026

- The shared adapter now reserves 463 UTF-8 bytes for bounded repair feedback
  before grouping or generation. Error detail is limited to 400 bytes, preserving
  valid UTF-8. Both attempts keep the same source; overflow still fails explicitly.
- Call policy identity changed so prior calls do not bypass the new reservation.
- All **75 backend checks passed**, including an exact-capacity Unicode repair
  boundary, source preservation, saved-call reuse, chronology and export checks.
- A genuine Qwen 4B generation probe deliberately failed its first validation with
  a 400-character Unicode error. The second attempt fit at 8,192 context/2,048
  output, retained the source, and completed. A subsequent call reused the saved
  result. Actual two-attempt elapsed time: **11.25 seconds**.
- This forced structural probe is not meeting-accuracy evidence. The resident
  runtime snapshot is recorded in the result; peak process memory was not measured.
- [Actual probe result](../evaluation/results/phase5/retry-probe.json).
  Source-ID citation handling and genuine AMI quality gates remain pending.

## 5.1 Source-ID evidence

- Documentation, reconciliation and notes now select stable segment IDs. Python
  attaches the unchanged source text; LLM contracts forbid generated quote fields.
  References outside each call's sources, duplicate IDs and unsupported literal
  owner/deadline fields are rejected. Canonical API/export contracts are unchanged.
- Source tables deduplicate evidence in reconciliation/notes requests. Prompt,
  schema and stage-policy changes invalidate affected call/checkpoint identities.
  Existing completed records remain readable and exportable.
- The first genuine synthetic run exposed excessive instruction overhead at 8K.
  It failed explicitly. Repeated prompt instructions were shortened; the retry
  reused genuine ASR/refinement and completed without increasing context.
- **76 backend checks passed.** The actual synthetic result has one supported
  Docker decision, one Maya/Friday task, faithful budget/negation notes and exact
  generated source quotations. All eight individual ZIP members match exports.
- [Actual synthetic result](../evaluation/results/phase5/source-id-synthetic.json).
  This does not establish representative accuracy; AMI and long-meeting gates
  remain open. Focused action extraction is the next implementation step.
