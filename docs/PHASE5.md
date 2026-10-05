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


## Focused extraction and conservative refinement (development checkpoint)

Action extraction now precedes notes, with a second source-based review call and
separate chronological reconciliation. Every call uses the same local 4B package;
no training, new weights, dependencies or cloud APIs were added. Immutable source
IDs are restricted by the actual schema. Canonical quotations include validated
character ranges; legacy records remain readable. Repair capacity remains reserved.

Refinement can accept a plausible spelling correction without a glossary only
when the replacement independently occurs in the immutable meeting text. Guards
reject role expansion, singular/plural rewriting, embedded numeric changes and
weekday/month changes. Raw text and edit audits remain intact. Authored positive
witness tests are regression evidence, not genuine ASR correction measurements.

79 backend checks pass; the frontend build passes; five fixture browser checks pass
(the genuine browser check was not enabled in this checkpoint). Readiness reports
real Parakeet and shared Qwen3.5 4B installed. A forced reasoning-mode probe exhausted
4,096 generated tokens without returning JSON; it is not enabled in production.

Genuine ES2002a component profiles v4-v7 still fail context or structural validation.
Their identities, errors and request counts are retained in
`evaluation/results/phase5/development-failures.json`. Increasing context alone did
not fix missing assignments. Invalid responses remain in the ignored local cache.

The first full production Runner run used 16,384 context / 3,072 output tokens:
21:12.64 audio, 257.90 seconds ASR decoding, 501.67 seconds full run. Aligned WER was
18.56% with normalization and excluded regions disclosed in the report. All eight
ZIP members matched individual exports. The final record still missed the interface
assignment (2/3 closing tasks), classified ten finance/brief statements as decisions,
and called the 50-million profit aim revenue. These are semantic failures despite
successful pipeline completion. This checkpoint does not close milestones 5.2-5.5.
The full measured output is retained as `full-es2002a-development-v8.json`.

## Context recovery and coupled consolidation (development)

The v9 ES2002a run hit a measured 18,385-byte consolidation reservation against
16,384 context. v10 reused verified ASR, refinement and 15 completed calls,
then finished with notes compression; its two tasks still missed the interface
assignment, and financial facts were lost. v11 completed but redistributed
summary citations onto unrelated speech. A finance-only appended ledger also
included unsupported interpretations and is removed.

The current reducer selects existing fact IDs; Python carries each selected
fact's text and evidence together. It cannot generate a new factual sentence or
redistribute its citations. Topic titles remain generated labels. Extraction
and interpretation accuracy still require source review. Dense review drafts
are split into chronological source groups before generation; no text is
silently truncated. Input enums, sentence character ranges, literal metadata
and unsupported profit/revenue-label checks remain enforced. Refinement and
 documentation policies have separate versions so a documentation-only fix
can reuse a verified refinement checkpoint.

The first genuine browser upload on this development version failed its task
count assertion: extraction found Maya's task, but review dropped it. Its
budget summary also invented a past correction. The original failed run is
preserved locally; it is not a browser pass. Review instructions are shortened
to preserve supported drafts, and notes now distinguish contrast from history.


84 backend tests and the WER counter examples pass. All six Playwright tests
pass, including genuine browser-created meeting
`a8c103e9-9b94-4210-84d4-de488bc5a75f`: real ASR, shared 4B stage provenance,
one Docker decision, Maya's reporting task, exact Docker quote/audio and JSON
matching the canonical record. The deadline assertion now expects the exact
source wording **by Friday**; the earlier format-only failure is retained.
Five other browser checks use labeled API fixtures. Desktop output was visually
inspected. This authored short recording is compatibility evidence, not AMI
meeting accuracy. The frontend build and offline dependency-lock check pass.

The passing browser compatibility run still invents a previous $50 budget in
its summary even though the recording only says "$15, not $50". It is a
semantic failure, and the compatibility pass does not close the history or
unsupported-claim gate. The frozen AMI candidate will be measured without
claiming release readiness.


ES2002a v12 failed after 14 completed calls because the financial guard rejected
"no explicit mention of profit/revenue" and "did not specify" as affirmative
category claims. The narrowly bounded absence patterns are now accepted;
"there was no profit" still requires an explicit source label. This fix arose
from ES2002a development, before any held-out LLM generation. Held-out ASR was
already started under the same ASR profile. Its saved genuine checkpoints will
be reused with their old identities disclosed; a revised LLM/source freeze is
recorded before held-out LLM generation. No held-out output drove this fix.


ES2002b failed after 28 completed calls because extraction repeated context-only
items. IS1000b failed after one call because review repeatedly emitted anonymous
owners. The latest development fix excludes context-only items from canonical
new actions while retaining original model proposals in call checkpoints and
counting exclusions in warnings. Chronological source processing still visits
every source unit. Unknown source IDs remain errors. Pronoun-only owners become
null at canonicalization; the original model field remains in its checkpoint.
No speaker/name is inferred. These changes follow the existing requirement for
unspecified ownership. 86 backend tests pass, including repeat deduplication,
anonymous ownership and preservation of original model output. No held-out LLM
output was used; the source/LLM freeze is amended before its first generation.


ES2002a policy 14 completed with 106 exact source references and matching exports,
but classified brief constraints as decisions and proposals as tasks. It also
exposed a software bug: correcting a candidate's extraction category was being
shown as meeting revision history. Policy 15 keeps those processing explanations
in resolution checkpoints instead; only actual source-supported temporal changes
can populate that audit. The existing reclassification test now asserts an empty
meeting audit, while cancellation/reassignment tests retain their source history.
This development-only fix precedes all held-out LLM generation. Semantic accuracy
failures remain failures; category/history separation is not an accuracy claim.


Post-evaluation delivery compatibility check found one of eleven existing
records could not be read: newer optional provenance fields changed the typed
serialization digest of its saved refinement. The reader now accepts the exact
stored serialization digest after validating that refinement, while retaining
source/quote checks. Unknown legacy sampling penalties stay null; new calls
record their actual options explicitly. A regression checks readable legacy
metadata and rejects changed provenance. 87 tests pass; all eleven existing
records remain readable without modifying their original artifacts. This is a
post-benchmark read-compatibility fix, not model/prompt tuning. Benchmark code
and the final held-out freeze remain identified in their recorded manifests.
