# AMI ES2002a public evaluation artifacts

Derived from the [AMI Meeting Corpus](https://groups.inf.ed.ac.uk/ami/corpus/),
AMI Project, Edinburgh/Idiap/TNO. Official manual annotations v1.6.2 and the
ES2002a mixed-headset signal are licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), as stated on the
[official download page](https://groups.inf.ed.ac.uk/ami/download/).

`manifest.json` records official URLs, source hashes and preparation details.
`manual.json` is a rendered orthographic transcript with actual annotation times;
punctuation is attached and nonlexical vocal events are excluded. Speaker labels
are absent from model text. `manual-source-map.json` preserves original speaker,
segment and word IDs for audit. `reference.json` is the official reference with
NXT source links, excluded from every model prompt. `raw.json` is genuine Parakeet
CPU INT8 inference on the entire WAV, including surrounding chatter outside the
main-meeting reference. No source audio, model weights or cache checkpoints are
included here.

Each model/profile directory contains actual outputs, failures, rejected API
responses, timings and model/provenance metadata. The 32K/4K primary and 48K/8K
secondary conditions use unchanged source inputs and production prompts/guards.
`protocol-freeze.json`, `followup-protocol.json` and the predeclared
[rubric](../../ami-es2002a-rubric.json) identify the protocol. The adaptive
follow-up is not a replacement for failed primary outcomes.

`semantic-review.json` is Codex's review against the annotations, not an independent
human score. The [report](../../../docs/AMI_ES2002A_EVALUATION.md) explains the
limits. The [readable 9B manual notes](qwen9-48k-manual-meeting.md) render the
actual validated record, including its missing tasks. Granite's one validated
record is empty. **No model produced a complete-quality meeting record.**

Revalidate the published copies from the repository root:

```powershell
.venv/Scripts/python.exe evaluation/verify_ami.py --root evaluation/results/ami-es2002a
```

Download and inference commands are in [evaluation/README.md](../../README.md).
The application defaults and distinct-weight Runner policy were not changed.
