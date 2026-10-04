# Five focused phases

Statuses describe actual work, not an estimate of model quality. Each phase has a local commit after its checks pass; coherent fixes receive separate commits.

| Phase | Deliverable | Exit gate | Status |
| --- | --- | --- | --- |
| 1. Design and contracts | This plan, complete design, model decisions, validated schemas, visual preview, repository conventions | Requirement traceability reviewed; contract checks pass; dependency specification recorded | Complete |
| 2. Audio and transcription | Dependency locks, bounded upload, FFmpeg preparation, timed ASR segments, saved raw transcript | Runtime installed/locked; invalid audio rejected; timing preserved; real Parakeet smoke test recorded | Complete; installed/locked runtime, real FFmpeg conversion and genuine Parakeet compatibility run recorded in PHASE2.md |
| 3. Refinement and documentation | Separate LLM checkpoints/prompts, edit guards, evidence validation, canonical exports, recoverable jobs | Semantic guard and API tests pass; genuine model execution is reported separately | Implementing; 58 automated checks pass, real Qwen checks underway |
| 4. Review workspace | Responsive, accessible upload/results UI, audio evidence navigation, progress, errors, exports | Production build passes; desktop and narrow viewport inspected | Planned |
| 5. Verification and delivery | Reproducible setup, sharable sample, actual outputs, evaluation report and demonstration | Real three-stage run; held-out English meeting checks; export consistency; documentation complete | Planned |

## Definition of done

An implemented adapter is not a verified model. Phase 5 remains open until real inference and representative meeting evaluation have been completed. Synthetic or stubbed test outputs must never be presented as real model results.

## Phase 1 verification, 4 October 2026

- Cloned the owner's empty repository; no pre-existing source or history was overwritten.
- Checked the source problem statement against the design's requirement map.
- Verified model availability against NVIDIA, Qwen, sherpa-onnx and Ollama primary documentation. The Qwen checkpoints are deployment defaults, not measured winners.
- Observed an RTX 4060 Laptop GPU with 8 GB VRAM; no performance claim follows from that observation.
- Ran `python -m unittest discover -s tests -v` using the available Python 3.12.14 interpreter and Pydantic: **5 tests passed**.
- Full `uv sync` failed when contacting PyPI: socket access was blocked by the current execution environment. Some core packages exist in the local cache, but the full ASR runtime does not. No runtime installation or lockfile is claimed. This is a Phase 2 prerequisite.
- No ASR or LLM inference has been run. No sample output or benchmark has been fabricated.
- Validated the static preview's HTML IDs and the Python project metadata; its local HTTP endpoint returned 200. Browser rendering inspection is pending because this session has no enabled browser surface. Desktop/mobile breakpoints are specified, not visually certified.

## Commit convention

Use messages such as `docs: define five-phase meeting assistant design`, `feat: add recorded audio transcription`, or `fix: reject unsupported evidence references`. Stage only files belonging to the change. Record verification in the phase log or evaluation report. Pushing to GitHub is a separate action requested by the owner.
