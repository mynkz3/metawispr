# Metawispr

A meeting workspace that turns uploaded English recordings into a raw transcript, a terminology-refined transcript, minutes, agreed decisions, and actionable tasks. Claims in the meeting record link back to their source audio.

**Build status:** phase 2's upload, audio preparation, Parakeet adapter, checkpoints, API, CLI and raw exports are implemented. **35 tests pass**. Real Parakeet inference, compressed-format conversion and the dependency lock remain unverified because this development environment blocks downloads. Refinement, documentation and the production UI are future phases. See [the design](docs/DESIGN.md), [phase gates](docs/PHASES.md) and [Phase 2 verification](docs/PHASE2.md). A model choice is not a measured quality result.

## Architecture

React + TypeScript interface → FastAPI → Parakeet v2 INT8 ONNX → Qwen3.5 4B terminology refinement → Qwen3.5 9B documentation → validation → Markdown / JSON / ZIP.

The two Qwen checkpoints are local deployment defaults pending project-specific evaluation. Only one ASR runs in the product. Faster-whisper large-v3 is an evaluation baseline.

## Development

Phase 2 requires Python 3.11–3.13 and uv. Model weights are installed separately and are not committed. Node.js and Ollama will be needed for later phases.

```sh
uv sync
uv run python -m unittest discover -s tests -v
uv run python -m metawispr download-model
uv run python -m metawispr doctor
uv run uvicorn metawispr.api:app --host 127.0.0.1 --port 8000 --workers 1
```

Run these commands from the repository root. Open `http://127.0.0.1:8000/docs` for an interactive upload/API interface. Use one server process; do not run the CLI against the same data directory while the server is processing meetings. The React review workspace will arrive in Phase 4.

Dependency resolution and initial weights require network access. PyPI and GitHub downloads were blocked in this session with `WinError 10013`; no lockfile or full runtime installation is claimed. Tests used public packages already available in the local cache, as recorded in [the verification report](docs/PHASE2.md). Resolve and commit `uv.lock` when installation succeeds. `.env.example` documents process environment overrides; Python does not automatically load `.env`.

## Transcribe a recording

```sh
uv run python -m metawispr transcribe /path/to/meeting.wav --title "Project planning"
uv run python -m metawispr retry MEETING_UUID
```

WAV, MP3, M4A, FLAC, OGG and WEBM are accepted, subject to decoder validation. The default limits are 200 MiB and 120 minutes, with three pending jobs including uploads and one inference worker. Already normalized mono 16 kHz, 16-bit PCM WAV needs no converter. Other inputs use a system FFmpeg or imageio-ffmpeg's bundled executable.

Each meeting has a generated UUID directory under `data/`, containing `meeting.json`, the original recording and `prepared.wav`. Successful ASR adds immutable `raw.json` and `raw.txt`. Raw JSON includes original/model hashes, runtime version, timings and audio-window offsets. Text is preserved exactly; timestamps identify windows and are **not word alignment**. `transcribed` means the first stage finished; full meeting documentation is not implemented yet.

For an offline model install, download the [official v2 INT8 archive](https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8.tar.bz2) on a network-enabled machine, then run:

```sh
uv run python -m metawispr download-model --archive /path/to/package.tar.bz2
```

An optional `--sha256 EXPECTED_HASH` checks a checksum you obtained independently. The installer records archive/file hashes and attribution, rejects unsafe archives, and never overwrites an existing model directory. `doctor` reports prerequisite availability; it does not certify model loading or recognition quality.

## API

| Method and path | Behavior |
| --- | --- |
| `GET /api/health` | Dependency/model prerequisites and configured limits |
| `POST /api/meetings` | Multipart `file`, optional `title` and `glossary`; returns 202 and UUID |
| `GET /api/meetings` | Recent local recordings |
| `GET /api/meetings/{id}` | Metadata/status and available raw transcript |
| `POST /api/meetings/{id}/retry` | Resume a retryable failure using saved checkpoints |
| `GET /api/meetings/{id}/audio` | Prepared WAV with browser byte-range playback |
| `GET /api/meetings/{id}/export/raw.txt` | Exact raw segment text |
| `GET /api/meetings/{id}/export/raw.json` | Canonical raw transcript and provenance |

The optional glossary is saved for Phase 3; it does not modify raw ASR text. A missing runtime/model produces a retryable setup failure with the recording retained. Invalid input requires a new upload. Restarting the server marks interrupted jobs as failed and eligible for explicit retry when the original exists. Exports and polling never invoke a model.

Open [the visual design preview](docs/ui-preview.html) in a browser to inspect the intended desktop/mobile layout. It is an explicitly labeled static design, not a working transcription interface.

## Scope and data

The initial release handles uploaded recordings. Live capture, speaker identity recognition, accounts, and public hosting are future work. Audio and transcripts stay in the configured local data directory; the default LLM server is local. Never commit personal recordings, model weights, or secrets.

Application code is MIT licensed. Model weights and third-party binaries retain their own licenses; see the design's model attribution section.
