# README screenshot provenance

The five screenshots were captured from Metawispr's current built UI against the
real local FastAPI endpoints, without synthetic HTTP fixtures or new inference.

- Recording: `ES2002a.Mix-Headset.wav`, AMI Meeting Corpus.
- Duration: 1272.64 seconds (21:12 displayed).
- Saved meeting: `1b9065ab-1064-41a6-9dd7-3961f02380ea`.
- Documentation completed: 2026-10-05; screenshots captured: 2026-10-08.
- ASR: NVIDIA Parakeet TDT 0.6B v2 INT8 ONNX, sherpa-onnx 1.13.8, CPU.
- LLM: Qwen3.5 4B through Ollama, Q4_K_M, runtime 0.35.1.
- GTCRN: not used in this historical run.
- Saved record: three summary points, three extracted decisions and four tasks.

The browser check compared rendered segment/item counts with saved artifacts,
opened a task's exact supporting quote, verified playback seek to its segment
start, and verified exported JSON matches the saved record. Crops focus on the
relevant interface panels; they omit some content below the visible crop. Source
times identify audio windows, not word-level alignment. These checks establish
UI/artifact compatibility, not correctness of the model's interpretation.

Source attribution: [AMI Meeting Corpus](https://groups.inf.ed.ac.uk/ami/corpus/),
the AMI project. The [official distribution](https://groups.inf.ed.ac.uk/ami/)
licenses its corpus under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Displayed transcripts are machine-generated from the recording; notes, decisions
and tasks are model-derived transformations. They are not the official reference
annotations. No audio files or model weights are included with these screenshots.
