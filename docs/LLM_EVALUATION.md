# Lightweight LLM regression comparison

5 October 2026. This report compares genuine local inference on authored English
transcript cases. It is a development regression study, not representative meeting
accuracy, an ASR benchmark, or a completed Phase 5 release evaluation.

## Protocol

The [corpus](../evaluation/cases.json) contains six refinement cases and ten
documentation cases, written before inference. Original corpus SHA-256:
`33585338c809d9c1d78a8d68ff8bb457dfed8ae15a785da8f9f5ec5a8c58dcc7`.
The [runner](../evaluation/run.py) uses production prompts, schemas, edit guards,
evidence checks, chronological reconciliation and notes consolidation. It does not
send reference answers to the model or ask another model to grade responses.

Main conditions: 8,192-token configured context, 2,048 output allowance,
temperature/seed zero, thinking disabled, presence penalty zero, repeat penalty
one, two attempts maximum. Every component case unloads its model before and after
execution. Inputs and settings are identical across models. Two cases use neutral
filler to force two bounded documentation groups. The same selected weights are
tested in both roles through component functions; the production Runner's
distinct-weight restriction and the application's defaults remain unchanged.

Hardware: Windows, Intel Core i7-14700HX, 28 logical processors, approximately
16 GB installed RAM, RTX 4060 Laptop GPU with 8 GB VRAM, Ollama 0.35.1. GPU runs
use Ollama's default offload, not a forced equal GPU-layer count. Qwen 9B reported
mixed CPU/GPU allocations, so this is a comparison of actual local deployment
behavior, not a controlled GPU-kernel speed comparison.

All **58 component cases** finished across the main comparison, 16K follow-up
and CPU subsets, using **98 genuine chat requests including retries**. The
[actual output reports](../evaluation/results/) preserve inputs, output records,
errors, timings and model metadata; [rejected responses](../evaluation/results/rejected-responses.json)
are retained separately and never presented as accepted meeting records. They
contain only these authored cases, not user recordings or model weights.

Exact artifacts: installed Qwen 4B digest `d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04`
(3.324 GB package), Qwen 9B digest `56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90`
(6.551 GB package), both Q4_K_M. Granite used IBM's official H-Micro Q4_K_M GGUF,
revision `dc1dd2585fac18a78001c677d33ef8a7bbb7eb68`, file SHA-256
`bcc78b9b25450101d1ad90d4b9a264e1bac892f534dfb76066f4eec792fdf023`,
1.943 GB. It was imported as `metawispr-granite4-h-micro:q4_k_m`, digest
`3fb76833e15c512f3c9e1187d620c97505f73273ee817c9900f8552de1de4ac3`;
Ollama reports 3.2B parameters, whereas IBM names the model a 3B model. The registry
pull repeatedly stalled, so its unfinished artifact was not evaluated. The
[pinned IBM source and checksum](../evaluation/results/granite-artifact.json)
identify the artifact actually tested.

## Main 8K observations

| Model | Refinement exact-reference cases | Documentation strict assertions | Validated documentation records | Median short-documentation component time |
| --- | --- | --- | --- | --- |
| Qwen3.5 4B Q4_K_M | 6/6 | 7/10 | 8/10 | 16.6 s |
| Qwen3.5 9B Q4_K_M | 6/6 | 8/10 | 9/10 | 32.0 s |
| Granite H-Micro 3B Q4_K_M | 6/6 | 0/10 | 7/10 | 8.0 s |

Timings above are medians across eight different short cases, each run once from
an unloaded model. They are not repeated medians of identical recordings, and do
not include ASR, uploads or the review UI.

**Strict assertion counts are not semantic accuracy.** In particular, Granite
often uses correct source quotes without their final punctuation. Full-sentence
reference anchors reject these legitimate variants, making its zero strict passes
an unsuitable stand-alone quality score. Selection below is based on reviewed
material failures as well as application outcomes, not that zero alone.

Both Qwen models corrected the three expected alias occurrences across the two
positive refinement cases without changing protected facts. Neither changed the
no-op, absent-glossary or untrusted-instruction cases. In the repeated-anchor case,
4B proposed an ambiguous correction which the application rejected; 9B proposed
no correction. The final text was preserved in both cases.

Qwen 4B captured the task to send an agenda but returned a null deadline despite
the explicit phrase `next Tuesday`. Qwen 9B preserved that phrase. The reviewed
short cases preserved missing owners, amounts, versions, negation and proposals;
neither turned the malicious example into a deletion assignment. Qwen 9B returned
no topic-minutes entries for the agenda case despite a correct summary/task.

The strict scorer also counts Qwen 9B's two supported withdrawal/cancellation
statements in its decisions array as unexpected rows: this corpus expects them
only in revision history. They are **not fabricated agreements**, and the original
Friday launch/report were not kept as active commitments. Thus strict pass counts
must not be presented as semantic accuracy or a universal model ranking.

Two Qwen 4B cross-group jobs and one Qwen 9B job stopped at the conservative input
capacity guard before final notes generation. Qwen 9B completed the 8K reassignment
case with the current Docker decision and only Omar's Tuesday checklist task.
Capacity failures count as failed application outcomes; they do not independently
measure the model's ability to interpret those inputs.

Granite's final refinement texts passed, but in the absent-glossary case it proposed
two unsupported grammar/pronoun rewrites, both blocked by the glossary guard. Its
documentation promoted `We could move to Kubernetes` into the decisions array and
treated the unapproved budget status as a decision. In the accepted 8K reassignment
record it retained **Sara's Friday task after the explicit reassignment to Omar
and Tuesday**, added a Docker status statement as a task, and omitted revision
history. These are material classification/chronology failures, not punctuation
differences. Three documentation jobs failed quote/literal-field/reconciliation
validation; rejected responses also retained cancelled commitments or copied an
absent calibration-example quote. The guards prevented those responses from
becoming records. Its concise summary/minutes sometimes omitted qualifying tasks
already present in its task array.

## Separate 16K follow-up

After the 8K failures, both chronological cases were run with a 16,384-token
context. References and semantic content stayed fixed; more neutral filler was
required to force two groups at the larger context. This is a separate condition,
not a replacement for the 8K observations.

Qwen 4B produced validated records for both cases. It removed superseded launch,
report, owner and deadline states, but duplicated Omar's current checklist task
using two different supporting quotes. Qwen 9B completed the withdrawal case but
duplicated the current log-check task; its reassignment failed after two invalid
reconciliation responses attempting to replace/retire unchanged current items.
The guard prevented those responses from becoming a canonical record.

One 4B log-check task is semantically correct with a later status quote, but fails
the scorer's predeclared original-quote anchor. This is a reference-alignment
limitation, not a missed log-check action. The scorer's raw precision/recall totals
remain preserved for audit and are not substituted for these reviewed findings.
Increasing context alone did not eliminate duplicate items or invalid reconciliation.
Granite failed both 16K jobs: reconciliation/literal-field checks in withdrawal,
and new evidence outside the supplied batches in final reassignment notes.

## CPU feasibility subset

Qwen 4B passed `protected_facts` and `explicit_commitments` with `num_gpu=0`.
Ollama reported zero GPU allocation for both calls. Observed refinement time:
17.5 s; observed documentation time: 89.5 s. This verifies two CPU component cases,
not a complete CPU-only audio pipeline or long-meeting throughput.

Its reported allocation was approximately 3.36 GB; available system RAM after
generation was approximately 1.5 GB on this 16 GB machine. Qwen GPU runs reported
approximately 3.34 GB total/VRAM for 4B and at most 6.38 GB total/5.60 GB VRAM for
9B at 8K. These are runtime-reported post-request allocations, not measured peak
process memory. They do not establish a hardware minimum.

Granite also produced validated outputs for both CPU subset jobs with zero GPU
allocation, approximately 2.24 GB reported allocation, 11.2 s refinement and
44.0 s documentation. Its exact-reference documentation assertion fails on quote
anchor formatting. The CPU record correctly identifies Docker and Maya/Friday,
but its minutes strengthen lack of deployment agreement to `No deployment tomorrow`.
Both CPU subsets contain one refinement case and one documentation case only.
Different output lengths affect elapsed time; these are feasibility observations,
not pure tokens-per-second comparisons or evidence that either model is ready
for arbitrary meetings.

## Recommendation

**Qwen 4B is the strongest lightweight single-model candidate in this study for
our current prompts and guards.** It costs more disk and time than Granite but
has fewer material documentation failures in the reviewed cases. Granite is not
a suitable drop-in for both roles under these conditions. That conclusion does
not rule out model-specific prompting/tuning and another controlled evaluation.

Qwen 9B handled the explicit relative deadline and the 8K reassignment better,
but still showed duplicate tasks, empty topic minutes, and invalid 16K reconciliation.
It is not a demonstrated universal winner, and the corpus does not establish
that two weights outperform one. Keep the current default while testing an optional
single-4B profile; do not declare that profile release-ready from these cases.

The subsequent [AMI ES2002a study](AMI_ES2002A_EVALUATION.md) tests genuine public
meeting audio and manual annotations. It does not validate the single-4B
preference: Qwen 9B alone produces nonempty validated manual notes, but omits the
assigned tasks, and no model meets complete meeting-record requirements. Keep
the authored-case recommendation scoped to this regression study.

Before changing the default, address explicit-deadline omissions, semantic task
duplication and consolidation capacity, then evaluate representative recordings
with reviewed references. Enabling the shared-weight production profile also
requires changing its deliberate distinct-weight policy and verifying an actual
audio-to-export run; this component experiment does not silently change that policy.

## Verification

The existing **71 backend tests passed**. The scorer's runnable checks, evaluation
script compilation, frozen-corpus SHA check, matched inputs/prompts/settings across
models, complete report counts and CPU zero-VRAM checks passed. The local API
remained ready, and Ollama reported no resident models after execution. No frontend
code, dependency lock or application defaults changed. Representative evaluation
and Phase 5 release gates remain open.

## Scope and remaining work

The source cases are authored and selected for specific failure modes. Some simple
examples resemble existing prompt calibration; they are not a held-out dataset.
This agent inspected generated summaries, minutes and extracted items. There is
no independent human-rated corpus, confidence interval, repeated-load benchmark,
accent/noise evaluation, WER measurement, or independent quality adjudication here.

The [evaluation instructions](../evaluation/README.md) explain scoring, retries,
provenance, separate CPU runs and checkpoint reuse. Successful generation,
evidence matching and exact-reference assertions are different checks. Model
selection for a public release still needs representative recordings and manual
reference annotations. The application defaults remain Qwen 4B refinement plus
Qwen 9B documentation after this comparison.
