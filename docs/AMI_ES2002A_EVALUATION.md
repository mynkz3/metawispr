# AMI ES2002a local model comparison

5 October 2026. Genuine local inference on one public English meeting, using
unmodified production prompts, contracts and validation. This is a development
evaluation of one selected meeting, not a corpus-wide or independently adjudicated
benchmark. The application defaults and distinct-weight policy remain unchanged.

**Qwen 9B produced the strongest validated narrative documentation, but none of
the three models produced a complete meeting record that meets our requirements.**
The earlier small-regression preference for a single Qwen 4B is not validated by
this meeting. Qwen 9B's successful manual-transcript record omitted all three
reference task assignments, and its real-ASR documentation still failed citation
validation. Keep the current model selections provisional; no shared-weight
profile is ready to replace the application default.

## Dataset and reference

[AMI Meeting Corpus](https://groups.inf.ed.ac.uk/ami/corpus/), meeting **ES2002a**,
mixed-headset WAV from the
[official signal mirror](https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/ES2002a/audio/).
The downloaded file measures **1,272.6 seconds (21 minutes 12.6 seconds)**; this
differs from the 1,242-second listing in the corpus signals table. The manual
annotations cover the main meeting from around 50 to 1,110 seconds. The whole WAV
also contains surrounding setup/closing conversation and is processed in the ASR
arm. Thus the manual and ASR arms are separate input conditions, each identical
across models; their latencies and unannotated peripheral content should not be
compared as if they used identical transcripts. No AMI word-error-rate claim is
made without a correctly aligned and scored reference region.

This is a four-person scenario meeting about designing a remote control. The
official v1.6.2 manual annotations contain **236 nonempty timed segments**, and
**3,105 word XML elements including punctuation**. Rendered text has approximately
2,600 whitespace-separated tokens. The parser follows inclusive NXT references,
reads the XML's declared encoding, verifies all word elements appear exactly once,
preserves case/disfluencies/contractions, attaches punctuation and excludes
nonlexical vocal events. Original overlapping segment times are retained. No
speaker labels or corpus role metadata are added to the text supplied to models.

The official abstract, actions, decisions, problems and links to source words are
retained for review, excluded from all model requests. The reference contains
three commercial requirements (25 Euro selling price, international sales,
production cost no greater than 12.50 Euro), three assigned responsibilities
(working design, technical functions, product requirements), and an unresolved
TV-only versus extra-functionality question. Commercial requirements originate
in the project brief; the decision annotations mark external decisions. The
reference is concise rather than an exhaustive set of all valid meeting facts.

Inputs, reference and the [review rubric](../evaluation/ami-es2002a-rubric.json)
were fixed before model inference. The scenario glossary contains ordinary domain
terms, without ASR-output-specific aliases. Reference and input hashes are
recorded in the provenance. Public AMI data may have appeared in pretraining;
this is not a guaranteed unseen model-training test.

## Protocol

- Same installed Q4_K_M Qwen3.5 4B, Qwen3.5 9B and official IBM Granite 4.0
  H-Micro GGUF artifacts as the [earlier regression study](LLM_EVALUATION.md).
- Same **32,768 context / 4,096 output allowance**, temperature/seed zero,
  thinking disabled, two-attempt maximum, automatic Ollama offload. The larger
  profile is an evaluation choice; no application default changed.
- Manual-transcript documentation arm isolates LLM extraction from ASR mistakes.
- Shared Parakeet CPU INT8 raw transcript feeds each model's own refinement,
  followed by that model's documentation, using production component functions.
  The production Runner's distinct-weight requirement is not bypassed in the app.
- Models run sequentially and unload before/after each stage. Multiple calls
  inside a stage share the loaded model. Latency includes loading, retries and
  reconciliation; it is one observation per condition, not a repeated benchmark.
- The 8K/2K application default requires **44 initial manual groups**, whereas
  this 32K/4K profile requires two. This is a deterministic capacity preflight,
  not an AMI inference result for the 8K profile.
- Schema validity, exact evidence matching and semantic faithfulness are reviewed
  separately. Failed responses remain failed, with their actual responses saved.

Machine: Intel Core i7-14700HX, approximately 16 GB RAM, RTX 4060 Laptop 8 GB,
Windows and local Ollama 0.35.1. Allocation observations are runtime-reported,
not independently sampled memory peaks. Mixed CPU/GPU offload can affect timing.

Parakeet used the production CPU INT8 deployment, four threads and 30-second
windows cut near low-energy pauses. Full-file preparation/transcription took
**250.0 seconds**, with **245.4 seconds** recorded decode time and **4.1 seconds**
model loading. It produced **44 nonempty segments**. These are genuine observed
timings for this one file. Key project prices, international scope and closing
responsibilities survive in the raw text; several surrounding/disfluent passages
remain unclear. This is not an ASR model comparison or official AMI WER result.

## Primary 32K/4K observations

| Model | Manual documentation | ASR refinement | ASR documentation | Documentation stage wall time, manual / ASR |
| --- | --- | --- | --- | --- |
| Qwen3.5 4B | Failed quote validation; retry blocked by byte guard | Complete | Failed quote validation twice | 83.2 / 124.8 s |
| Qwen3.5 9B | Failed quote validation; retry blocked by byte guard | Complete | Failed quote validation twice | 273.5 / 388.1 s |
| Granite H-Micro | Failed quote validation; retry blocked by byte guard | Complete | Validated but empty record | 24.0 / 20.1 s |

These times describe success/failure outcomes with different generated lengths,
not pure speed or accuracy measurements. There were **12 genuine requests** in
this condition: one manual request, one refinement request and two ASR
documentation requests per model. Three refinements and one empty documentation
artifact completed; five documentation jobs failed. No complete useful record
was obtained in this primary condition.

All manual first responses stopped normally, rather than exhausting the output
allowance. Their invalid quotes triggered feedback, but adding feedback exceeded
the conservative input bound before a second request could be made. This is an
application retry-budget limitation, separate from the models' quote mistakes.
The 4B model merged/rewrote disfluent quotes and attached a quote to the wrong
segment. Both Qwen ASR arms also misattributed or changed quotes. Granite's first
responses used string `"null"` assignment fields and broad compound "decisions";
its accepted ASR retry returned all factual arrays empty and only the uncertainty
`What did you get?`. Passing structural/provenance checks therefore did not yield
a usable meeting record.

Qwen 4B accepted one role expansion, `user interface` to `user interface designer`.
It preserves the role indicated by the reference, but is normalization rather than
recovery of a demonstrated ASR miss. Its reason incorrectly claimed an explicit
glossary alias, although the supplied glossary had no aliases. Six other proposals
were rejected as unchanged, absent or ambiguous. Qwen 9B accepted/proposed no edits;
Granite's unchanged proposal was rejected. This meeting and narrow glossary do not
establish terminology-correction recall or comparative refinement superiority.

## Separate 48K/8K follow-up

After both Qwen manual jobs could not fit feedback, a secondary protocol was
fixed before its inference: **49,152 context / 8,192 output allowance**, unchanged
source transcripts, glossary, semantic rubric, prompts and validation. All three
models use the same larger profile. Both manual and ASR documentation inputs now
fit one initial group. This removes hierarchical consolidation and gives retry
and output headroom; it changes two resource settings and cannot attribute any
improvement to context alone. Original 32K outcomes remain preserved.

| Model | Manual documentation | ASR refinement | ASR documentation | Documentation stage wall time, manual / ASR |
| --- | --- | --- | --- | --- |
| Qwen3.5 4B | Failed owner-evidence/quote checks twice | Complete | Failed quote checks twice | 134.7 / 121.0 s |
| Qwen3.5 9B | Validated narrative; all three tasks omitted | Complete | Failed quote checks twice | 388.0 / 550.2 s |
| Granite H-Micro | Failed quote checks twice | Complete | Failed quote checks twice | 37.4 / 29.1 s |

Qwen 9B's validated manual output has nine summary points and six topic sections.
It preserves 25 Euro, the 12.50 Euro production cap, the 50 million Euro target,
international-market discussion and unresolved TV-only scope. It returns
**`tasks: []` despite the explicit closing assignments**, and `decisions: []`.
Commercial requirements originate in the brief, so keeping them in minutes rather
than labelling them newly agreed decisions is consistent with the production
prompt's conservative classification. Task omission is a separate real coverage
failure. The model's `10 to 12` clock paraphrase is less clear than the source
`ten to twelve`; role/speaker-boundary interpretation and the selected evidence
still require human review. Exact quote validation does not certify every claim.
The isolated `expert.` utterance belongs to Andrew in AMI's source mapping
(speaker D, m0010), but the output attaches that qualifier to Craig. The main role
mapping is otherwise preserved; matching quote strings cannot verify speaker binding.

Qwen 4B's first full-manual response identifies the three responsibilities and
correct names, but does not quote the names in those tasks' supporting evidence.
This is an owner-provenance failure, not proof that the names were fabricated.
Its retry still changes/merges an assignment quote and drops the interface task.
The ASR responses repeatedly reference a design-process sentence using the wrong
segment ID, with other changed or cross-segment quotes. They never become accepted
meeting records. Enlarging context alone did not resolve these errors.

Granite's rejected follow-up responses combine broad discussion into asserted
decisions, invent touchless-control scope and an unsupported next-meeting timestamp
`2025-08-27T10:00:00`, and copy the excluded prompt example `We agree to use Kubernetes`.
Other responses assign completed attendance/whiteboard activities as current tasks
or use string `"null"` instead of JSON null. Guards reject these responses; the
32K empty artifact is not evidence of useful extraction. Granite is not a suitable
drop-in for our two roles with these prompts.

Runtime-reported post-request allocation at 32K / 48K was approximately **4.10 /
4.65 GB** for 4B, **7.34 / 7.98 GB total** for 9B (approximately **5.58 / 5.54 GB
VRAM**, with CPU offload), and **2.49 / 2.91 GB** for Granite. These are not peak
memory measurements or hardware minimums. The larger context made 9B slower on
this machine. Its manual 48K request reported 11,744 prompt tokens; 4B reported
5,388 prompt tokens for its ASR documentation. The requested large context also
works around the application's conservative byte budget; it does not show that
the models inherently need 48K tokens for this meeting.

## Judgment and next engineering work

For further documentation development, **Qwen 9B is the strongest candidate among
these three under this pipeline**, because it alone returns a nonempty validated
manual record with useful financial/design notes. That does not make it the best
complete meeting assistant: all three task assignments are missing, the full
ASR-derived chain fails, and the 9B CPU offload has a substantial latency cost.
Qwen 4B remains a cheaper refinement/development option, but this meeting does not
demonstrate comparative refinement accuracy: essential domain terms are already
recognized and the fixed glossary permits little actual repair.

Before selecting a production winner:

1. Reserve retry-feedback capacity when constructing groups; replace unnecessary
   byte-budget fragmentation with a verified token budget or a smaller payload.
2. Make action/owner/deadline extraction explicit and separately reviewable before
   narrative generation; test role-based assignments as well as named commitments.
3. Improve exact citation handling, including adjacent-segment boundaries. Preserve
   rejected outputs and do not silently rewrite unsupported quotes into evidence.
4. Re-evaluate the unchanged reference, then use additional meetings with reviewed
   annotations. Once prompts are tuned using ES2002a, it is a development case;
   public-corpus pretraining exposure remains unknown.

The mixed 4B-refinement/9B-documentation application baseline was not executed in
this comparison. These experiments call production components with one selected
weight set per chain and do not establish that a shared model outperforms that
baseline. There is no independent human rater, confidence interval, repeated
latency benchmark, full CPU LLM evaluation or official AMI ASR score here.

## Verification and artifacts

All **18 component jobs** across two matched conditions finished, making **26
genuine chat requests**. **Eight artifacts completed** (six refinements, one empty
Granite record, one nonempty Qwen 9B manual record); **ten documentation jobs failed**.
All **18 rejected responses** are retained in their reports. Successful structure
and evidence matching are kept distinct from semantic completeness.

The **71 backend tests passed**, as did parser/range/complete-word coverage checks,
Python compilation, frozen input/reference checks and revalidation of all completed
artifacts. The verifier checks model metadata, shared inputs/options within each
condition, source hashes, accepted-edit replay and exact evidence. No application,
frontend or dependency defaults changed. Phase 5 release evaluation remains open.

[Published public inputs, genuine outputs and semantic review](../evaluation/results/ami-es2002a/)
include provenance and reproduction instructions. Original WAV/ZIP, runtime
checkpoints, model weights and local logs remain ignored. The readable
[Qwen 9B manual notes](../evaluation/results/ami-es2002a/qwen9-48k-manual-meeting.md)
are a rendering of the actual validated record, with its task omissions visible.

## Attribution and reproduction

AMI Project, Edinburgh/Idiap/TNO. Official annotations and signals are distributed
under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), as stated on the
[official download page](https://groups.inf.ed.ac.uk/ami/download/). Derived public
text/reference artifacts preserve attribution; audio, weights and caches remain
outside Git. Commands are in [evaluation/README.md](../evaluation/README.md).
