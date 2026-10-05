# Workplan within the meeting-assistant problem statement

5 October 2026. This is the remaining work inside **Phase 5**. Phases 1-4 are
implementation history, not evidence that the current model profile meets the
accuracy requirements. The milestones below are planned; this document does not
claim that their fixes or quality gates have passed.

## Scope and model roles

Source: the owner's `ML Bootcamp.pdf`, read in full, including the rendered model,
rubric and output tables. This plan references its sections without republishing
the source PDF. The requirements are for uploaded English recordings, genuine
transcription, domain-aware correction, structured minutes/decisions/tasks, an
interactive interface, downloads and a demonstration on new audio.

Runtime order remains:

**Upload -> Parakeet raw transcript -> Qwen 4B refinement -> Qwen 4B documentation
-> validation -> review and exports.**

The documentation stage may make focused extraction, reconciliation and writing
calls. These are internal steps of that stage; documentation always consumes the
refined transcript, and cannot bypass refinement or mutate the raw transcript.

The statement says the two LLM roles must be distinct processing stages, and also
uses the wording "separate language model" in its objectives and functional
requirements. Our implementation interpretation is two separate LLM role runs
sharing `qwen3.5:4b`, with independent prompts, schemas, context and saved artifacts.
Different checkpoint weights are not explicitly specified. The submission must
disclose this shared-weight choice and identify both roles; we must not describe
two different installed models or claim organizer approval of this interpretation.

Owner constraints: keep Parakeet INT8 and the installed Qwen 4B Q4_K_M; current
model storage is approximately 3.99 GB. No additional weights or training are part
of this plan. Context starts at 8,192 with a 2,048 output allowance; resource
changes require measured memory and quality results, not advertised maximums.

Live capture, diarization, cloud/API providers, accounts, integrations, custom
model training, vector databases, another model sweep and a UI redesign are
deferred. Improvements to the existing review/error/export flow remain in scope.

## Requirement coverage

| ID | Problem-statement requirement | Remaining milestone and evidence |
| --- | --- | --- |
| R1 | English audio upload and genuine raw transcription (§3, §4) | 5.4: complete audio runs; compare ASR against reviewed audio/reference |
| R2 | Unsupported, empty or unreadable files have clear errors (§3, §4) | 5.1 and 5.5: existing boundary/error checks remain passing; inspect UI errors |
| R3 | Domain terminology corrected without changing intent (§4) | 5.3: actual error/correction review; protected facts; accepted/rejected edit audit |
| R4 | Separate ordered ASR/refinement/documentation stages (§3, §4) | Every milestone: independent prompts/artifacts/provenance; one upload runs all stages |
| R5 | Raw and refined transcripts both retained and displayed (§3, §4, §6) | 5.3 and 5.5: immutable raw bytes; comparison and both downloads |
| R6 | Concise summary and organized minutes (§4, §6) | 5.2 and 5.4: main-topic coverage and faithful wording against the source |
| R7 | Agreed decisions and assigned tasks; no proposal promoted to agreement (§4, §6) | 5.2 and 5.4: reviewed precision/recall, revisions and empty-list cases |
| R8 | Owners/deadlines only when stated; missing details unspecified (§1, §4, §6) | 5.2 and 5.4: quoted support, correct attribution, null and relative-date cases |
| R9 | Interactive upload/status/review/downloads (§4) | 5.5: genuine browser run and accessible desktop/phone checks |
| R10 | Required outputs downloadable; readable/structured records agree (§6) | 5.5: raw, refined, minutes, decisions and tasks visible/downloadable; JSON/Markdown/ZIP parity |
| R11 | New outputs generated for previously unseen audio (§3, §5) | 5.4: frozen configuration on held-out recordings; no recording-specific code or answers |
| R12 | Source/prompts/dependencies/setup, model description, shareable sample and demonstration (Deliverables) | 5.5: complete submission checklist and actual matching artifacts |

Rubric: ASR 20, refinement 20, minutes/decisions 25, tasks 15, application 15,
submission 5. Extraction fidelity and genuine terminology correction therefore
take priority over adding product features.

## Current evidence and failures

- Shared-4B execution, readiness, source validation and export parity work on the
  short synthetic sample. All 74 backend tests, the build and five fixture browser
  checks passed at the shared-4B migration commit.
- The genuine browser quality assertion failed: a stated budget became an agreed
  decision. The CLI summary also added an unsupported budget-change history.
- AMI ES2002a exposed wrong/rewritten/cross-segment quotes, missing owner support,
  missed assignments, and a retry that could not fit validation feedback. Neither
  expanding context nor the tested larger model solved complete-record quality.
- Genuine domain-error correction remains insufficiently measured. Important AMI
  terms were already recognized; a role expansion is not proof of ASR error repair.
- Glossary-less refinement executes the model but currently accepts no edits.
  The problem statement does not require a supplied glossary; that limitation
  needs genuine context-only correction cases rather than a claim of full coverage.

See [shared-4B verification](SHARED_QWEN4B.md), [AMI results](AMI_ES2002A_EVALUATION.md)
and [the regression study](LLM_EVALUATION.md). Existing failures remain preserved.

## Five remaining milestones

### 5.1 Source evidence and context reliability

**Purpose:** make supported extraction possible within the existing memory budget.

- Fix capacity reservation in the shared generation/grouping path for refinement,
  extraction, reconciliation and notes. Reserve the actual maximum feedback bytes,
  system/schema/chat framing and output allowance before accepting a group.
- Keep chronological source coverage; no silent truncation or skipped segments.
  Oversized inputs must fail clearly, and successful calls must remain reusable.
- Let documentation select stable source-unit IDs and let Python construct exact
  quotations. Start with existing segment IDs; introduce smaller immutable source
  units only if needed. Do not ask 4B to count character offsets or retype evidence.
- An item crossing a segment boundary uses multiple real source references.
  Unknown IDs, changed text and unsupported owner/deadline fields remain invalid.
  Matching evidence proves traceability, not semantic correctness.
- Version affected prompts/contracts/policies so saved calls cannot be reused
  under changed behavior. Preserve existing completed artifacts and raw hashes.

**Exit gate:** meaningful boundary/retry and source-ID tests pass; a real repair
request fits its unchanged source; chronology, invalid-reference rejection,
checkpoint reuse and exports remain correct. Record actual model requests and
memory; do not raise context merely to hide a budgeting error.

**Likely files:** `llm.py`, `documentation.py`, affected schemas/prompts and their
existing tests. Reuse the current adapter/store; no new orchestration dependency.

### 5.2 Accurate meeting documentation

**Purpose:** fix the demonstrated decision/task errors, covering the 40-point
minutes/decisions and action-item rubric categories.

- Extract decisions, assignments and later revisions before narrative writing.
  Use a focused response contract. Summary generation must not create, drop or
  rewrite the resolved canonical decisions/tasks.
- Distinguish facts, proposals, explicit agreements, current assignments and
  completed activities. A budget statement belongs in notes unless agreement is
  supported. Do not invent a prior amount, cancellation or change history.
- Preserve stated role owners. Resolve a role to a name only with supporting
  introduction/assignment context and correct attribution; uncertainty stays
  unspecified. No speaker identity recognition is required.
- Preserve relative deadline wording. Never infer a calendar date from upload
  time. Include the evidence establishing each owner and deadline.
- Reuse the existing chronological reconciliation and revision audit for changes,
  cancellation and reassignment. Merge genuine duplicates without removing
  distinct assignments. Supply needed earlier context with its source references.
- Keep empty decisions/tasks valid when none exist. An empty response is not a
  quality pass on a meeting with reviewed assignments. Use reviewed generic
  calibration examples; never put ES2002a's answers into production prompts/code.

**Exit gate:** the genuine synthetic/browser sample returns only its supported
Docker decision and the Maya/Friday task, with faithful budget/negation notes.
ES2002a development runs retain all three explicit closing assignments and the
important commercial requirements in appropriate notes. Quotes are source-valid;
role/name/deadline interpretation is reviewed. Proposal, no-assignment, revision
and cross-group cases pass. Schema completion alone cannot close this milestone.

**Likely files:** `documentation.py`, schemas, documentation/reconciliation/notes
prompts, and focused existing regression/browser checks.

### 5.3 Genuine and conservative terminology refinement

**Purpose:** satisfy the correction requirement, rather than showing an unchanged
transcript and claiming successful refinement.

- Review genuine ASR terminology errors against the recording/reference. Include
  technical terms and acronyms, ambiguous terms and already-correct negative cases.
  Manufactured transcript corruptions are regression fixtures, not ASR evidence.
- Use meeting context and the current canonical glossary/explicit-alias mechanism.
  Keep exact unique anchors and the existing numeric/negation/commitment guards.
- Treat the glossary as optional assistance, not a new prerequisite for meeting
  upload. Test genuine errors with and without it. If the current glossary-only
  acceptance policy blocks the required context-aware correction, revise that
  policy minimally with audited proposals and focused tests; ambiguous changes
  must remain rejected. Do not accept arbitrary model rewrites as a shortcut.
- Reject unrelated rewriting and role completion presented as an error correction.
  Zero accepted edits is valid for already-correct input and is reported as such.
- Preserve all raw text, edit offsets, rejection reasons and source hashes. Check
  names, numerical facts, deadlines and commitments for introduced changes.

**Exit gate:** real corrections have reviewed audio support, measured correction
precision/recall and false-edit counts; no introduced protected-fact changes in
the release cases. Context-only and glossary-assisted cases are exercised;
already-correct/ambiguous cases remain faithful. If no genuine
errors occur in a recording, correction recall is not applicable, not 100%.

**Likely files:** the existing refiner/guards/prompt and regression cases. No
keyword classifier or fine-tuning is introduced.

### 5.4 Complete-pipeline evaluation on new recordings

**Purpose:** establish performance against recordings, not only component fixtures.

- Use ES2002a as development data. Add two development recordings covering genuine
  terminology errors and proposal/assignment/revision behavior. Reserve two
  different meeting-series or fresh recordings for final evaluation, including
  one newly recorded shareable English meeting when available.
- Freeze recording IDs/hashes, glossary, model digest, prompts, settings, reference
  rules and acceptance targets before final held-out execution. Keep related
  meetings together. Public AMI pretraining exposure is unknown; it cannot be
  advertised as guaranteed unseen by the model.
- Run uploaded audio through the actual Runner/API with shared 4B, not only manual
  transcript components. Use manual transcripts separately to diagnose ASR versus
  documentation errors. Grade each output against the evidence actually available
  at that stage, and also review the final record against the recording.
- Measure ASR WER on correctly aligned annotated regions, disclose exclusions,
  and separately inspect critical names/terms/numbers/negation. Measure refinement
  correction/false-edit counts; task and decision precision/recall; owner/deadline
  accuracy and coverage; unsupported claims; key-topic coverage and export parity.
- Record latency, resident/peak memory where measured, load/retry counts, hardware
  and all failures. State unavailable measurements plainly. Code coverage, exact
  citations, another LLM's approval and empty output are not semantic grading.

**Planned engineering targets, not problem-statement thresholds:** task and
decision precision >=95% and recall >=90% on the reviewed final set; no invented
assignments/owners/deadlines, unsupported agreed decisions or introduced
protected-fact changes;
100% valid source references and export parity. Report denominators, per-meeting
counts and N/A categories. All explicit critical assignments and main financial/
negation facts in the named development cases must be retained accurately.

**Exit gate:** the reviewed references and frozen targets are met on the real
development and held-out runs, with at least one successful new-recording
end-to-end demonstration. A missed target remains an open failure. If held-out
results drive another change, that recording becomes development data and a new
held-out recording is needed. Small-sample results are not a general accuracy
guarantee or proof of minimum hardware requirements.

**Likely files:** the existing evaluation runner/reports, reviewed reference
artifacts and a new Phase 5 result log. Another ASR/model comparison is optional
future research and does not block the required workflow.

### 5.5 Review, exports and submission

**Purpose:** deliver the already-built product with accurate, reproducible results.

- Keep the existing aesthetic workspace. Verify upload, ordered status, clear
  errors/retry, raw/refined comparison, source playback, minutes, decisions/tasks
  and null fields. Fix observed interaction issues; do not redesign the interface.
- Re-run the genuine browser quality test with its assertions intact. Verify every
  required output is visible/downloadable and JSON/Markdown/ZIP derive from the
  same canonical record. Saved-stage exports must work without loading an LLM.
- Provide the complete source, prompts, dependency locks and setup/run README;
  describe the STT checkpoint and both shared-4B LLM roles accurately.
- Provide at least one shareable recording and its actual raw/refined transcripts,
  minutes, decisions and tasks. For licensed public audio, supply its official
  download, checksum and attribution; an authorized delivery bundle may carry
  audio separately. Keep model weights, caches and private recordings outside Git.
- Produce an actual upload-to-download demonstration matching the sample's
  input/output hashes. Keep fixtures clearly labelled. Retain limitations and
  measured results in the technical description; do not substitute authored answers.

**Exit gate:** Milestones 5.1-5.4 pass; backend/build/browser checks pass; the
delivery checklist is complete; documented clean setup and a new English recording
work through genuine inference and consistent exports.

## Execution and change control

Execute **5.1 -> 5.2 -> 5.3 -> 5.4 -> 5.5**. This orders implementation by observed
failures; runtime stage order is unchanged. Dataset/reference preparation can
proceed independently, but final held-out execution waits for a frozen pipeline.

For each coherent change: trace affected callers, implement the smallest fix,
run meaningful tests and the relevant genuine case, record pass/failure evidence,
then make a local commit. A failed quality assertion stays visible and cannot be
relaxed simply to make the build green. Push only when the owner requests it.

Every new task must map to R1-R12 or an observed failure blocking those requirements.
Otherwise defer it. Do not claim Phase 5 complete until the real accuracy and
delivery gates pass. At this planning commit all five milestones remain open;
no inference, dependencies, weights or application behavior changed.
