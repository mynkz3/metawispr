# Genuine Gemini compatibility attempts

These reports use the existing authored 14.997-second speech sample described
in the project's browser compatibility checks. They are real Parakeet CUDA and
Gemini API runs, not synthetic API fixtures or representative meeting scores.

- `initial.json`: ASR, refinement and two documentation calls completed; the
  following Gemini request returned HTTP 503. No complete document or exports.
- `retry-1.json`: saved successful checkpoints reused; HTTP 503 recurred before
  a canonical document was produced. Its wall time covers the retry only;
  retained ASR/refinement timings are historical.

These are failure evidence. There is no Gemini winner claim, WER improvement
claim or semantic pass. Credentials and audio files are excluded. Model response
versions, source hashes and successful-call provenance remain in the reports.
