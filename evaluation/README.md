# Local LLM component comparison

This is a fixed, hand-authored regression suite with genuine inference. It is not
a representative meeting benchmark, an ASR evaluation, or a production profile
switch. The application defaults and distinct-weight Runner policy remain unchanged.

The 6 refinement and 10 documentation cases were written before model execution.
They exercise aliases, protected facts, no-op/absent-glossary behavior, repeated
anchors, proposals, missing fields, relative deadlines, multiple owners, untrusted
instructions, and within/across-group cancellations and reassignment. Neutral
filler deterministically forces two documentation groups in two cases. Every model
gets the same expanded inputs, production prompts, JSON schemas, guards, context
(8,192), output allowance (2,048), temperature (0), seed (0) and two-attempt limit.
Thinking is disabled. Models unload before/after each component case so observations
include loading. Stage inputs have explicit authored provenance and no invented ASR
metadata; synthetic segment times have no corresponding recording.

Run from the repository root after installing its locked environment and starting
local Ollama. Model weights and detailed checkpoints remain outside Git.

```sh
python evaluation/check_scoring.py
ollama pull granite4:3b-h
python evaluation/run.py --model qwen3.5:4b --output .cache/evaluation/qwen4-gpu/results.json
python evaluation/run.py --model qwen3.5:9b --output .cache/evaluation/qwen9-gpu/results.json
python evaluation/run.py --model granite4:3b-h --output .cache/evaluation/granite-gpu/results.json
```

The completed [5 October study](../docs/LLM_EVALUATION.md) used a pinned IBM GGUF
after the registry pull stalled. Its [artifact metadata](results/granite-artifact.json)
provides the exact download URL, revision and SHA-256. Verify the checksum, write a
Modelfile containing `FROM "<absolute path to the verified GGUF>"`, then import it:

```sh
ollama create metawispr-granite4-h-micro:q4_k_m -f <path-to-Modelfile>
python evaluation/run.py --model metawispr-granite4-h-micro:q4_k_m --output .cache/evaluation/granite-gpu/results.json
```

This local tag is an alias for that imported official artifact, not an upstream
registry release. The registry tag in the generic example may resolve different
weights. Check recorded digests when attempting an exact reproduction. To reproduce
the separate 16K follow-up, set `METAWISPR_LLM_CONTEXT=16384`, select the two
`cross_group_*` case IDs explicitly, and use an isolated output directory. Filler
expansion changes with context, so compare only matched conditions across models.

For a separate small CPU feasibility check, pass `--cpu` and an isolated output
path. This sets `num_gpu=0`; verify returned resident-model allocation reports
zero GPU bytes. Subsets must be reported with their actual case count.

```sh
python evaluation/run.py --model granite4:3b-h --cpu --cases protected_facts explicit_commitments --output .cache/evaluation/granite-cpu/results.json
```

Each finished case records its output, errors, attempts, provenance, elapsed wall
time and actual Ollama response durations. The report stores model digests,
quantization, package bytes, input/prompt identity, and runtime/hardware metadata.
Interrupted runs resume successful generation checkpoints; replayed timings are
not fresh inference timings. Completed report cases are not rerun or silently
replaced. Use a new output directory for changed conditions or a fresh repeat.

Refinement passes only when the final segment strings exactly equal their reference.
Documentation scoring uses predeclared action/entity patterns plus supporting quote
anchors, one-to-one item matching, exact nullable owner/deadline fields, and revision
anchor coverage. Failed generations count as failed cases and omitted reference
items, not as successful empty records. These mechanical assertions are not a
semantic judge: manually inspect all outputs, including summary and minutes, before
making a recommendation. Do not infer corpus-wide accuracy from this small suite.
Full-sentence anchors can reject valid partial quotes or a later status quote for
the same action. Supported cancellation decisions can differ from the corpus's
revision-only convention. Preserve the mechanical scores and document those
reference limitations separately; do not describe every unmatched row as invented.

The published JSON files contain genuine outputs for authored source cases and
separately labelled rejected responses. They are reproducible review artifacts;
runtime checkpoints, downloads and private user recordings are not published.

Ollama resident `size`/`size_vram` are runtime-reported allocations after requests,
not independently sampled peak process RAM/VRAM. Available system RAM is measured
before/after calls on Windows and includes unrelated applications. No minimum
hardware specification follows from either observation. Latencies are single-pass
cold component observations; they are not repeated medians for identical recordings
or end-to-end meeting turnaround times.

## AMI ES2002a comparison

`ami.py` reads official NXT annotations directly with Python's standard library.
It preserves every annotated word exactly once, retains real overlapping segment
times, and adds no speaker labels or hidden reference summaries to model text.
Download the official files into the ignored cache (PowerShell example):

```powershell
New-Item -ItemType Directory -Force .cache/ami/es2002a | Out-Null
curl.exe --fail --location --output .cache/ami/ami_public_manual_1.6.2.zip https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/ami_public_manual_1.6.2.zip
curl.exe --fail --location --output .cache/ami/es2002a/ES2002a.Mix-Headset.wav https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/ES2002a/audio/ES2002a.Mix-Headset.wav
.venv/Scripts/python.exe evaluation/ami.py prepare
.venv/Scripts/python.exe evaluation/check_ami.py
.venv/Scripts/python.exe evaluation/ami.py asr
.venv/Scripts/python.exe evaluation/ami.py run --model qwen3.5:4b --output .cache/ami/es2002a/qwen4-32k/results.json
.venv/Scripts/python.exe evaluation/ami.py run --model qwen3.5:9b --output .cache/ami/es2002a/qwen9-32k/results.json
.venv/Scripts/python.exe evaluation/ami.py run --model metawispr-granite4-h-micro:q4_k_m --output .cache/ami/es2002a/granite-32k/results.json
```

Run models sequentially. All models receive the same manual-documentation input
and the same genuine Parakeet raw input. The second arm runs the selected weights
in refinement, then documentation through component functions; it does not alter
the application's distinct-weight Runner policy. A failed refinement prevents its
documentation stage. The official abstract/actions/decisions/problems and source
links are reference-only. The predeclared `ami-es2002a-rubric.json` governs review;
do not send it to a model or mistake literal quote matching for semantic correctness.

The default evaluation profile is **32K context, 4K output**, temperature/seed zero,
thinking disabled and two attempts. This is deliberately separate from the app's
8K/2K default. The conservative byte guard would split the manual transcript into
44 groups at that default, versus two groups in this profile. Models unload before
and after each stage, not between a stage's grouped calls. Checkpoints and rejected
responses are preserved. Changing settings/weights/inputs requires a new output
path; resumed checkpoint timings are not fresh-run timings.

The [AMI corpus](https://groups.inf.ed.ac.uk/ami/corpus/) and its official v1.6.2
annotations/signals are released under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Credit the AMI Project
and preserve source attribution for derived transcripts/reference annotations.
Keep WAV files and original annotation ZIPs outside Git. ES2002a is one selected
public scenario meeting; it cannot establish corpus-wide accuracy or guarantee
absence from model pretraining.

The completed [ES2002a report](../docs/AMI_ES2002A_EVALUATION.md) also records an
adaptive matched **48K/8K** follow-up, fixed before that condition's inference.
Repeat all three `run` commands with `--context 49152 --tokens 8192`, using new
`qwen4-48k`, `qwen9-48k` and `granite-48k` output directories. Inputs are unchanged;
there is no filler or prompt adjustment. Both inputs fit a single documentation
group in this condition. Run the saved-artifact verifier after all comparisons:

```powershell
.venv/Scripts/python.exe evaluation/verify_ami.py
```

Public inputs, actual model responses and the semantic review are in
[results/ami-es2002a](results/ami-es2002a/). One Qwen 9B manual record is nonempty
and validated but misses the assigned tasks. The validated Granite record is empty.
Neither should be presented as a complete-quality meeting result.
