# Retired hybrid experiment

GLiNER2, DeBERTa and the experimental task ledger were removed on 7 October
2026 at the owner's request. The single ES2002a experiment did not produce a
validated meeting record or demonstrate an overall accuracy benefit. Component
NLI scores are not ground-truth accuracy measurements.

The active pipeline is Parakeet CUDA followed by shared local Qwen3.5 4B
refinement and documentation, with the existing Qwen claim audit. No model
training or prompt tuning was performed during retirement.

Historical reports remain in `evaluation/results/hybrid-es2002a.json` and
`evaluation/results/hybrid-es2002a-setup-blocked.json`. See [PHASE5.md](PHASE5.md)
for the run outcomes and limitations. Hybrid weights, dependencies, execution
code and experiment-only working caches are removed.
