# Metawispr

A meeting workspace that turns uploaded English recordings into a raw transcript, a terminology-refined transcript, minutes, agreed decisions, and actionable tasks. Claims in the meeting record link back to their source audio.

**Build status:** phase 1 design and contracts are implemented. The audio pipeline, model execution, and production UI belong to the following phases and are not implemented yet. See [the design](docs/DESIGN.md) and [phase gates](docs/PHASES.md). A model choice is not a measured quality result.

## Architecture

React + TypeScript interface → FastAPI → Parakeet v2 INT8 ONNX → Qwen3.5 4B terminology refinement → Qwen3.5 9B documentation → validation → Markdown / JSON / ZIP.

The two Qwen checkpoints are local deployment defaults pending project-specific evaluation. Only one ASR runs in the product. Faster-whisper large-v3 is an evaluation baseline.

## Development

Python 3.11–3.13, Node.js 22.12+ or 24, and Ollama are required. Model weights are installed separately and are not committed.

```sh
uv sync
uv run python -m unittest discover -s tests -v
```

Dependency resolution requires network access. The first development session could not reach PyPI, so no lockfile or installed full runtime is claimed. The five contract tests were run with an existing Python 3.12 / Pydantic installation. Frontend and model setup instructions will be added with their implementation phases. `.env.example` documents environment overrides; Python does not automatically load `.env`.

Open [the visual design preview](docs/ui-preview.html) in a browser to inspect the intended desktop/mobile layout. It is an explicitly labeled static design, not a working transcription interface.

## Scope and data

The initial release handles uploaded recordings. Live capture, speaker identity recognition, accounts, and public hosting are future work. Audio and transcripts stay in the configured local data directory; the default LLM server is local. Never commit personal recordings, model weights, or secrets.

Application code is MIT licensed. Model weights and third-party binaries retain their own licenses; see the design's model attribution section.
