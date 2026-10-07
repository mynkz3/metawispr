# Metawispr

**Active profile (7 October 2026):** Parakeet CUDA + local Qwen3.5 4B for both
ordered LLM stages. Gemini integration and its private key were removed at the
owner's request. Historical evaluation reports are retained; accuracy gates
remain open. See [the shared Qwen profile](docs/SHARED_QWEN4B.md).

A meeting workspace that turns uploaded English recordings into a raw transcript, a terminology-refined transcript, minutes, agreed decisions, and actionable tasks. Claims in the meeting record link back to their source audio.

**Build status:** the recorded-meeting pipeline and responsive React review workspace are implemented. **74 backend tests pass**; frontend build, browser behavior, accessibility and real model compatibility are documented in the phase logs. See [the design](docs/DESIGN.md), [phase gates](docs/PHASES.md), [Phase 2 verification](docs/PHASE2.md), [Phase 3 verification](docs/PHASE3.md) and [Phase 4 plan/verification](docs/PHASE4.md). Representative meeting-quality evaluation remains Phase 5 work.

## Architecture

React + TypeScript interface → FastAPI → Parakeet v2 INT8 ONNX → Qwen3.5 4B terminology refinement → Qwen3.5 4B documentation → validation → Markdown / JSON / ZIP.

One Qwen 4B weight set serves both ordered LLM stages with separate prompts, schemas, checkpoints and provenance. This owner-selected default reduces model storage to approximately 4 GB including Parakeet; dependencies and caches are additional. It is not a claim of release-ready meeting accuracy. See the [shared-4B profile and improvement plan](docs/SHARED_QWEN4B.md). Only one ASR runs in the product. Faster-whisper large-v3 is an evaluation baseline.

The shared-4B switch passed backend tests, build, readiness and genuine synthetic audio/export checks. Five browser fixture checks passed; the genuine browser test failed its decision-quality assertion because 4B classified a budget fact as an agreed decision. That failure is retained and remains Phase 5 work.

The [active workplan](docs/WORKPLAN.md) keeps the remaining work inside the original
problem statement: source/context reliability, accurate meeting documentation,
genuine terminology refinement, new-recording evaluation, and review/export delivery.
It defines acceptance gates and preserves both LLM stages while sharing 4B weights.

A [genuine local LLM regression comparison](docs/LLM_EVALUATION.md) covers Qwen 4B, Qwen 9B and Granite H-Micro 3B on fixed authored cases, plus CPU subsets. It identified Qwen 4B as a lightweight candidate; the later shared-4B default is a separate storage decision. The [evaluation runner and actual outputs](evaluation/README.md) are included. These results do not establish representative meeting accuracy.

The [real AMI ES2002a comparison](docs/AMI_ES2002A_EVALUATION.md) now tests the same models on a 21-minute recording and official manual transcript. Qwen 9B produced the strongest validated narrative notes, but omitted the assigned tasks; no model met the complete meeting-record quality requirements. The earlier single-4B preference is not validated by this meeting. Citation handling, action extraction and context budgeting need work before selecting a production winner. Public derived inputs and genuine outputs are included; audio and weights remain outside Git.

## Development

Use Python 3.11–3.13, uv and a current local Ollama installation supporting Qwen3.5. Model weights are installed separately and are not committed. Use Node.js 22.12+ (24 LTS recommended) and npm to build the frontend.

```sh
uv sync --locked
uv run python -m unittest discover -s tests -v
uv run python -m metawispr download-model
ollama pull qwen3.5:4b
uv run python -m metawispr doctor
cd frontend
npm ci
npm run build
cd ..
uv run uvicorn metawispr.api:app --host 127.0.0.1 --port 8000 --workers 1
```

Start these commands from the repository root. Open **http://127.0.0.1:8000** for the workspace, or `/docs` for the interactive API. The frontend build is served by the same local process; build it before starting/restarting the server. Use one server process; do not run the CLI against the same data directory while the server is processing meetings. During frontend development, `npm run dev` in `frontend/` proxies API requests to the server on port 8000.

Start Ollama locally before `doctor`/processing; a standalone installation uses `ollama serve`. Dependency installation and initial weight downloads require network access. Reviewed network exceptions resolved the earlier sandbox block. `uv.lock` records the installed dependency set. On Windows, the matching sherpa binary package supplies the correct ONNX Runtime; no system DLL replacement is needed. `.env.example` documents process environment overrides; Python does not automatically load `.env`.

## Process or transcribe a recording

```sh
uv run python -m metawispr process /path/to/meeting.mp3 --title "Project planning" --glossary "Docker"
uv run python -m metawispr transcribe /path/to/meeting.wav --title "Project planning"
uv run python -m metawispr document MEETING_UUID
uv run python -m metawispr retry MEETING_UUID
uv run python -m metawispr export MEETING_UUID --output ./exports/meeting
```

WAV, MP3, M4A, FLAC, OGG and WEBM are accepted, subject to decoder validation. The default limits are 200 MiB and 120 minutes, with three pending jobs including uploads and one inference worker. Already normalized mono 16 kHz, 16-bit PCM WAV needs no converter. Other inputs use a system FFmpeg or imageio-ffmpeg's bundled executable.

Each meeting has a generated UUID directory under `data/`, containing metadata, original recording and `prepared.wav`. ASR adds immutable `raw.json` and `raw.txt`, including hashes, runtime, timings and audio-window offsets. Text is preserved exactly; timestamps identify windows and are **not word alignment**. `transcribe` stops at `transcribed`; `process` and API uploads continue to `complete`, adding `refined.json`, its accepted/rejected edit audit, `document.json`, and successful per-call checkpoints. Text/Markdown/JSON/ZIP downloads render from validated artifacts.

Use one canonical glossary term per line, optionally `alias => canonical`. Without a glossary, the refinement model still runs but no terminology edits are accepted. Raw output is always retained. Exact evidence matching helps trace claims; it does not certify a model's interpretation. Review decisions, tasks and revision notes before relying on them.

LLMs run sequentially and unload between roles. Defaults are 8,192 context tokens, 2,048 output tokens, a 300-second request timeout and at most two validation attempts. Bounded chronological groups reconcile every candidate decision/task, then consolidate notes for long meetings. Withdrawn/replaced items retain a separate source-backed revision history. Dense final records or a large individual segment/glossary can exceed the context and fail explicitly; increase `METAWISPR_LLM_CONTEXT` within available memory or submit a shorter recording. The duration ceiling does not guarantee arbitrary information density fits the default context.

For an offline model install, download the [official v2 INT8 archive](https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8.tar.bz2) on a network-enabled machine, then run:

```sh
uv run python -m metawispr download-model --archive /path/to/package.tar.bz2
```

An optional `--sha256 EXPECTED_HASH` checks a checksum you obtained independently. The installer records archive/file hashes and attribution, rejects unsafe archives, and never overwrites an existing model directory. `doctor` reports prerequisites for both LLM roles, which share one installed model by default; `doctor --asr-only` checks the ASR setup independently. Neither certifies recognition or extraction quality.

## API

| Method and path | Behavior |
| --- | --- |
| `GET /api/health` | Dependency/model prerequisites and configured limits |
| `POST /api/meetings` | Multipart `file`, optional `title` and `glossary`; returns 202 and UUID |
| `GET /api/meetings` | Recent local recordings |
| `GET /api/meetings/{id}` | Metadata/status, raw/refined transcripts and validated record |
| `POST /api/meetings/{id}/retry` | Resume a retryable failure using saved checkpoints |
| `POST /api/meetings/{id}/document` | Continue an ASR-only meeting through both LLM stages |
| `GET /api/meetings/{id}/audio` | Prepared WAV with browser byte-range playback |
| `GET /api/meetings/{id}/export/raw.txt` | Exact raw segment text |
| `GET /api/meetings/{id}/export/raw.json` | Canonical raw transcript and provenance |
| `GET /api/meetings/{id}/export/{format}` | `refined.txt`, `refined.json`, `edits.json`, `meeting.md`, `meeting.json`, `provenance.json`, `bundle.zip` |

A missing runtime/model produces a retryable setup failure with completed stages retained. Successful LLM calls are reused by input/prompt/schema/model digest/runtime/settings identity. Invalid input requires a new upload. Restarting the server marks interrupted jobs as failed and eligible for explicit retry when the original exists. Changing a completed stage's policy requires restoring its settings or submitting a new meeting. Raw downloads remain available after downstream failures. Exports and polling never invoke a model.

## Workspace checks

With the built app running on port 8000:

```sh
cd frontend
npm run check
npx playwright install chromium
npm test
```

The five default browser checks use explicitly synthetic API fixtures. The real local-model browser check is opt-in: set `METAWISPR_SMOKE_AUDIO` to a path containing the authored spoken compatibility sample in [PHASE2.md](docs/PHASE2.md) and `METAWISPR_SMOKE_ID` to a complete saved record of that same sample, then run `npm test`. It performs one new genuine upload and checks the sample's expected decision/task, provenance and downloaded JSON. Other arbitrary recordings need their own reviewed expectations. `METAWISPR_UI_URL` can override the test server URL. Screenshots are saved under `.cache/ui-qa/`, outside Git. This is compatibility and UI verification, not a representative model benchmark.

The workspace supports file selection/drop, optional glossary, saved progress/retry, source quotes with coarse audio-window navigation, raw/refined transcripts, correction/revision history and canonical downloads. Task fields are read-only; unspecified assignments/dates remain unspecified. Keyboard tabs and narrow layouts are supported. The [earlier static preview](docs/ui-preview.html) remains a labelled design artifact.

## Scope and data

The initial release handles uploaded recordings. Live capture, speaker identity recognition, accounts, and public hosting are future work. Audio and transcripts stay in the configured local data directory; the default LLM server is local. Never commit personal recordings, model weights, or secrets.

Application code is MIT licensed. Model weights and third-party binaries retain their own licenses; see the design's model attribution section.
