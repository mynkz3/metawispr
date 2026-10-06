# Genuine Gemini compatibility attempts

These reports use the existing authored 14.997-second speech sample described
in the project's browser compatibility checks. They are real Parakeet CUDA and
Gemini API runs, not synthetic API fixtures or representative meeting scores.

- `initial.json`: ASR, refinement and two documentation calls completed; the
  following Gemini request returned HTTP 503. No complete document or exports.
- `retry-1.json`: saved successful checkpoints reused; HTTP 503 recurred before
  a canonical document was produced. Its wall time covers the retry only;
  retained ASR/refinement timings are historical.
- `retry-2.json` and `diagnostic-attempt.json`: further explicit owner-requested
  checks, still stopped at the same call. `provider-error.json` records Google's
  structured UNAVAILABLE/high-demand message, without request headers or keys.

A separate tiny genuine JSON generation subsequently succeeded with STOP,
9 reported input tokens and 9 reported candidate tokens. The selected model
metadata was available. This establishes working generation access at that moment,
not remaining daily quota or successful meeting documentation. No quota-exhaustion
error was observed. Exact project quotas require the AI Studio dashboard.

These are failure evidence. There is no Gemini winner claim, WER improvement
claim or semantic pass. Credentials and audio files are excluded. Model response
versions, source hashes and successful-call provenance remain in the reports.
