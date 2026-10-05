# Gemini Flash profile

The owner selected Gemini Flash on 6 October 2026, temporarily setting aside
Qwen. The default environment profile uses Parakeet CUDA, then
`gemini-3.8-flash` for both ordered refinement and documentation stages.
Qwen weights and historical results are retained. No weights are downloaded for
Gemini and no new Python dependency is required: the adapter uses existing httpx.

## Setup

Obtain an API key from [Google AI Studio](https://aistudio.google.com/apikey).
Set `GEMINI_API_KEY` in the environment of the backend process using your local
secret-management method. Never paste the key into the browser, a tracked file,
an issue, or evaluation reports. The application reads process environment; it
does not automatically load `.env` files. `.env.example` is a configuration guide.

From the repository root, in the same environment containing your key:

```powershell
$env:METAWISPR_LLM_BACKEND = 'gemini'
$env:METAWISPR_REFINER_MODEL = 'gemini-3.8-flash'
$env:METAWISPR_DOCUMENTER_MODEL = 'gemini-3.8-flash'
$env:METAWISPR_ASR_PROVIDER = 'cuda'
.venv/Scripts/python.exe -m metawispr doctor
.venv/Scripts/python.exe -m uvicorn metawispr.api:app --host 127.0.0.1 --port 8000
```

Restart an existing server to apply environment changes, after its work queue
is idle. CUDA requires the compatible sherpa-onnx GPU runtime and CUDA/cuDNN
libraries established during the GPU setup; a CPU-only dependency installation
does not provide that runtime. CPU fallback is rejected. Use readiness and a
genuine ASR smoke run to verify your machine rather than assuming configuration
proves execution.

Audio is transcribed locally; transcript text, glossary, title and bounded
generation inputs are sent to Google's API. Saved artifacts remain local.
The review UI discloses this behavior. Google's free-tier quotas and data-use
terms differ from the paid tier; inspect your project's actual access and terms.
The adapter never switches to Qwen automatically on quota, authentication,
network, safety or validation failure. Completed stages remain saved.

## Generation and provenance

The adapter reuses production schema validation, semantic guards, UTF-8-bounded
repair feedback, at most two validation attempts and immutable call checkpoints.
Only normally finished, validated responses become successful checkpoints.
Blocked or truncated responses cannot become successful empty records.

The initial profile keeps the existing conservative 16,384 context reservation
and 3,072 output budget, temperature zero and seed zero. It requests Gemini's
LOW thinking level without returned thoughts. Reasoning is enabled; it is not
recorded as Ollama's disabled-thinking profile. Thought token usage is recorded
when reported. Output limits may include reasoning overhead, so a truncated
response remains a visible failure. A seed does not guarantee repeatability.

Wire requests use the Gemini REST API, JSON response schemas, server-side API-key
headers and the fixed Google HTTPS endpoint. API keys never enter checkpoint
identities or reports. Errors expose an actionable HTTP status without provider
messages that might echo credentials or meeting content.

Gemini does not disclose its weight digest, quantization or parameter count.
`metadata_sha256:` identifies a hash of returned model metadata, **not weights**.
Each call also records the response's model version when supplied. Hosted models
can change; metadata hashing is not an immutable checkpoint of cloud weights.
New provider policies and call identities prevent Qwen output reuse as Gemini.
Historical records remain readable; use a new meeting/run for a provider change.

## Evaluation

Keep only ES2002a and IS1000b active. Both are previously inspected development
meetings. The existing Phase 5 runner and terminology probe now select the active
provider and record API request durations, token usage and reported model versions.
They do not report local GPU residency for the remote LLM. Frozen historical
protocols are not rewritten; declare the Gemini experiment separately.

Run a genuine short authored recording first, then the two AMI evaluations with
new output directories and the unchanged reviewed references. The existing
`--reuse-asr` option can reuse verified GPU ASR; do not reuse Qwen refinement.
Disclose cache reuse and distinguish raw WER from documentation quality.
Compare task/decision precision and recall, unsupported claims, metadata,
terminology, completion, latency and token usage. This integration alone does
not establish Gemini as the winner or close Phase 5 accuracy gates.

## Return to Qwen explicitly

```powershell
$env:METAWISPR_LLM_BACKEND = 'ollama'
$env:METAWISPR_REFINER_MODEL = 'qwen3.5:4b'
$env:METAWISPR_DOCUMENTER_MODEL = 'qwen3.5:4b'
```

Restart the idle server with those settings. Qwen is not deleted.

## Verification record

Implementation checks use clearly synthetic HTTP responses. They cover actual
request construction, source-ID schemas, both ordered pipeline stages, checkpoint
reuse, semantic rejection, blocked/truncated output, quota errors, missing keys
and credential exclusion. These are software tests, not genuine Gemini inference.
Genuine inference and two-meeting semantic scoring are pending an API key.

On this host, 101 backend tests passed, the production frontend build passed,
and six browser checks passed (five existing fixtures plus the cloud-disclosure
fixture). The genuine model browser check was skipped. The restarted local
service reported Gemini selected, missing-key readiness, CUDA ASR readiness and
14 readable saved meeting records. WER/scorer counter checks passed. No genuine
Gemini request, accuracy score or paid usage is claimed.

Official sources checked on 6 October 2026:
- [Gemini Flash model](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)
- [REST generation](https://ai.google.dev/api/generate-content)
- [Model metadata](https://ai.google.dev/api/models)
- [Structured outputs](https://ai.google.dev/gemini-api/docs/structured-output)
- [Pricing and data use](https://ai.google.dev/gemini-api/docs/pricing)
- [Project rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
