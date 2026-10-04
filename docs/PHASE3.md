# Phase 3 implementation and verification

5 October 2026. The two local LLM stages, bounded processing, validation, recovery and exports are implemented. Genuine three-stage execution and actual HTTP exports passed the compatibility check below. Representative quality evaluation remains Phase 5 work.

## Implemented behavior

- Local HTTPX Ollama adapter: schema-constrained JSON, thinking disabled, temperature 0, seed 0, configured 8,192-token context and 2,048 output tokens, bounded timeout and at most two validation attempts. No cloud fallback or ambient proxy forwarding.
- Distinct configured tags and resolved model digests are required. Installed-model metadata and runtime version are saved with prompt/schema/input hashes and call timings/token counts.
- Qwen3.5 4B proposes exact original terminology anchors. Python resolves only unique anchors into original offsets; glossary, spelling/alias, word-boundary, overlap and protected number/negation/commitment guards produce an accepted/rejected audit. Raw output is immutable.
- Qwen3.5 9B extracts evidence-backed summaries, topic minutes, agreed decisions and tasks. Owners/deadlines must be null or literal complete text in supporting quotes. Relative deadlines remain unchanged.
- Long inputs use bounded chronological groups and adjacent hierarchical consolidation. A typed reconciliation call must account for every candidate decision/task exactly once (keep, retire or replace), using later source evidence for changes. A separate notes-only call writes summary/topics without overwriting resolved decisions/tasks. Original and later quotes are retained in `revision_audit`; capacity overflow fails clearly rather than dropping text.
- One worker runs stages sequentially. Native ASR weights are released before LLM work; each LLM unloads explicitly before the next stage. Atomic successful-call checkpoints allow a failed consolidation to reuse its extraction calls.
- Markdown, JSON, ZIP, raw/refined transcripts, edit audit and provenance all render from validated artifacts. Raw exports survive downstream artifact failures. Exports and polling do not invoke models.
- API uploads run the full pipeline. CLI `transcribe` stops at ASR; `process` runs all stages; `document` continues an ASR-only meeting; `retry` preserves the requested target. Interrupted LLM stages become explicit retryable failures on restart.

## Automated checks actually run

`python -m unittest discover -s tests -q`: **69 passed** after integration, with the installed and locked runtime. Coverage includes protected edits, exact/ambiguous anchors, fabricated owner fragments, invalid evidence, same-weight aliases, capacity overflow, truncated responses, bounded retries, model/input-aware call reuse, stage recovery, recovered completion timestamps, raw immutability, original/prepared source changes and nonempty canonical ZIP/JSON/Markdown parity. Explicit test doubles exercise workflow behavior; they do not establish model semantics. Compilation and `uv lock --check --offline` also passed using the workspace cache.

Chronological tests cover complete candidate coverage, later-evidence retirement, reassignment, null-field preservation, unchanged replacement normalization, explicit decision-to-task reclassification and successful call reuse after interruption. Scripted responses are explicitly test fixtures. Representative cross-group interpretation still requires real meeting evaluation. Failed model responses are saved only in the private local stage directory for debugging; they never become canonical artifacts.

## Genuine terminology probe

The official Ollama v0.35.1 portable Windows runtime was downloaded and verified against the release's SHA-256 digest before execution. It runs on `127.0.0.1:11434`, with cloud disabled and weights in the ignored workspace models directory.

Actual refiner: `qwen3.5:4b`, resolved digest `d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04`, parameter metadata `4.2B`, quantization `Q4_K_M`.

A **hand-authored transcript**, deliberately separate from ASR evaluation, contained `We agreed to use dock her. The budget is 15, not 50.` with glossary `Docker`. The initial offset-generating prompt produced inaccurate offsets; the guard would reject the edit. The final anchor-based prompt produced one accepted edit at Python offsets `[17,25)`, resulting in `We agreed to use Docker. The budget is 15, not 50.` No other text changed. Actual call duration: 5.4657 s, 416 prompt tokens, 46 generated tokens, one attempt. This is a tiny compatibility probe, not a terminology-accuracy benchmark.

## Genuine full-pipeline execution

The 14.997-second synthetic spoken meeting described in PHASE2.md ran through real Parakeet, Qwen3.5 4B, Qwen3.5 9B and validation. Actual final record:

- Decision: **Use Docker for the release.** Quote: `We agreed to use Docker for the release.`
- Task: **Maya will send the report by Friday.** Owner `Maya`; deadline `Friday`; identical source quote.
- `$15, not $50` remained in the summary/minutes, preserving the budget correction.
- `We have not agreed to deploy tomorrow` remained minutes, without an agreed deployment decision or task.

All evidence referenced `s00001` and matched the refined transcript exactly. The already-correct raw text stayed unchanged; the final refiner proposed no edits.

Actual documenter: `qwen3.5:9b`, digest `56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90`, metadata `9.0B`, `Q4_K_M`, Ollama 0.35.1. Observed run: ASR load 2.1199 s, decode 0.6467 s; refinement call 6.0465 s; documentation call 34.1848 s (1,192 prompt tokens, 919 generated tokens, one attempt); approximately 43.4 s from upload to completion. These are one short compatibility run on the development laptop, not latency or quality benchmarks.

Manual review of the first genuine run caught omitted decisions/tasks despite correct minutes. The prompt now explicitly requires those facts in their respective arrays and includes proposal/commitment calibration. Generation explicitly disables presence/repetition penalties that discourage copying repeated evidence. The rerun produced the decision/task above. One successful rerun does not establish omission rates on representative meetings.

Actual final artifacts remain in ignored `data/d4c22935-8d47-42b8-a438-c2f23f51e157/`; CLI exports were also generated locally. A real loopback Uvicorn server returned health/detail/JSON/Markdown/ZIP successfully. Downloaded ZIP JSON matched API decisions/tasks; its Markdown matched the Markdown endpoint byte-for-byte. An actual audio-range request returned 206 and the correct prepared bytes. `ollama ps` showed no model resident after the stages unloaded.

## Genuine chronological component probe

A separate **hand-authored two-group transcript** used neutral filler to exercise bounded grouping. It was not an ASR recording or a meeting benchmark. Real Qwen calls extracted both groups, reconciled candidates and consolidated notes. Earlier launch/report commitments were explicitly withdrawn/cancelled later; the final current decisions were empty, the unassigned log-check task retained null owner/deadline, and Alex’s draft task retained its explicit Monday deadline. Five revision-audit entries retained source evidence. All four successful documentation calls replayed from validated checkpoints on a second run.

Initial real probes exposed incorrect free-form consolidation: retained withdrawn items or omitted an unassigned task. The final implementation separates complete candidate reconciliation from notes generation. One intermediate response also labeled an unchanged new task as a replacement; identical replacements now preserve the validated original instead of failing the entire record. Tests cover this case. Matching and ordering source quotes still do not prove a cancellation refers to the intended candidate; human review remains necessary.

## Practical limits

Exact evidence proves traceability, not entailment. A model can still misinterpret a matched quote; decisions, tasks and revisions require review. The prompt treats transcript/glossary text as untrusted data, but prompt policy is not a formal semantic guarantee. No speaker identities, dates or missing assignment details are inferred.

Conservative context bounds can reject dense meetings before the audio-duration ceiling. Increasing context increases memory requirements; do not promise that an arbitrary two-hour record fits the default context. UI review and versioned user corrections are separate work.

Primary implementation references: [Ollama chat API](https://docs.ollama.com/api/chat), [structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [installed-model metadata](https://docs.ollama.com/api/tags), [official 4B package](https://ollama.com/library/qwen3.5:4b), [official 9B package](https://ollama.com/library/qwen3.5:9b).
