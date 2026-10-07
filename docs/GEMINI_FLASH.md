# Retired Gemini experiment

The owner retired Gemini integration on 7 October 2026 and returned to local
Qwen3.5 4B for both ordered LLM stages. Parakeet CUDA remains active.
The Gemini adapter, provider-selection controls, key-file reader and cloud UI
setup were removed. The private repository credential was removed. The active
application makes no Google API requests. Removing a local key copy does not
revoke the key at its provider.

Historical genuine reports remain in
[evaluation/results/gemini-compatibility](../evaluation/results/gemini-compatibility/).
The approximately 15-second authored recording completed CUDA ASR, one Gemini
refinement call and two documentation calls. Subsequent documentation requests
repeatedly returned HTTP 503 UNAVAILABLE with a high-demand message. A tiny JSON
generation succeeded. No complete Gemini meeting record, verified exports or
representative accuracy score was obtained.

These reports document the retired experiment, not active setup instructions
or a quality win. Historical remote call metadata remains readable. The current
implementation uses prompts, schemas, evidence validation and checkpoints with
the original local Qwen weights; no fine-tuning was performed.
