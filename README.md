# Metawispr

A meeting workspace that turns uploaded English recordings into a raw transcript, a terminology-refined transcript, minutes, agreed decisions, and actionable tasks. Claims in the meeting record link back to their source audio.

**Build status:** recorded audio, separate LLM stages, guarded refinement, evidence validation, resumable checkpoints and exports are implemented. **69 tests pass**. The Python runtime is locked; genuine FFmpeg/Parakeet execution and a real three-model synthetic meeting run passed compatibility checks, including actual HTTP exports. The React review workspace follows in Phase 4. See [the design](docs/DESIGN.md), [phase gates](docs/PHASES.md), [Phase 2 verification](docs/PHASE2.md) and [Phase 3 verification](docs/PHASE3.md). Model compatibility does not establish representative meeting quality.

## Architecture

React + TypeScript interface → FastAPI → Parakeet v2 INT8 ONNX → Qwen3.5 4B terminology refinement → Qwen3.5 9B documentation → validation → Markdown / JSON / ZIP.

The two Qwen checkpoints are local deployment defaults pending project-specific evaluation. Only one ASR runs in the product. Faster-whisper large-v3 is an evaluation baseline.

## Development

Use Python 3.11–3.13, uv and a current local Ollama installation supporting Qwen3.5. Model weights are installed separately and are not committed. Node.js is needed for the Phase 4 frontend.

```sh
uv sync --locked
uv run python -m unittest discover -s tests -v
uv run python -m metawispr download-model
ollama pull qwen3.5:4b
ollama pull qwen3.5:9b
uv run python -m metawispr doctor
uv run uvicorn metawispr.api:app --host 127.0.0.1 --port 8000 --workers 1
```

Run these commands from the repository root. Open `http://127.0.0.1:8000/docs` for an interactive upload/API interface. Use one server process; do not run the CLI against the same data directory while the server is processing meetings. The React review workspace will arrive in Phase 4.

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

LLMs run sequentially and unload between roles. Defaults are 8,192 context tokens, 2,048 output tokens, a 300-second request timeout and at most two validation attempts. Bounded chronological groups consolidate for long meetings. Dense final records or a large individual segment/glossary can exceed the context and fail explicitly; increase `METAWISPR_LLM_CONTEXT` within available memory or submit a shorter recording. The duration ceiling does not guarantee arbitrary information density fits the default context.

For an offline model install, download the [official v2 INT8 archive](https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8.tar.bz2) on a network-enabled machine, then run:

```sh
uv run python -m metawispr download-model --archive /path/to/package.tar.bz2
```

An optional `--sha256 EXPECTED_HASH` checks a checksum you obtained independently. The installer records archive/file hashes and attribution, rejects unsafe archives, and never overwrites an existing model directory. `doctor` reports prerequisites, including two installed distinct LLM digests; `doctor --asr-only` checks the ASR setup independently. Neither certifies recognition or extraction quality.

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

Open [the visual design preview](docs/ui-preview.html) in a browser to inspect the intended desktop/mobile layout. It is an explicitly labeled static design, not a working transcription interface.

## Scope and data

The initial release handles uploaded recordings. Live capture, speaker identity recognition, accounts, and public hosting are future work. Audio and transcripts stay in the configured local data directory; the default LLM server is local. Never commit personal recordings, model weights, or secrets.

Application code is MIT licensed. Model weights and third-party binaries retain their own licenses; see the design's model attribution section.
