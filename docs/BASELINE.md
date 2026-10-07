# Fixed ES2002a baseline

The owner selected the older Parakeet-based run as the historical baseline on
7 October 2026. Exact values, measurement scope and source SHA256 hashes are
saved in [baseline-es2002a.json](../evaluation/baseline-es2002a.json).

| Metric | Fixed predicted-transcript baseline | Manual-transcript comparison |
| --- | --- | --- |
| Aligned WER | 18.7% | ASR bypassed |
| Correct / extracted tasks | 2 / 15 | 3 / 5 |
| Task precision | 13.3% | 60% |
| Task recall | 66.7% | 100% |
| Correct owners | 0 / 2 | 0 / 3 |
| Correct deadlines | 0 / 2 | 0 / 3 |
| Unsupported notes | 9 / 24 | 7 / 24 |
| Unsupported topic titles | 2 | 1 |
| Topic coverage | 2 / 5 | 4 / 5 |

These are provisional agent-reviewed documentation scores. WER is measured
only over the aligned interval described in the JSON. The manual comparison
also includes the newer claim audit and a validator repair, so it does not
isolate transcription quality. Keep the historical baseline unchanged.
Future audio-preprocessing comparisons must hold the evaluation interval,
reference, WER normalization and ASR settings constant. No run was performed
to record this baseline.
