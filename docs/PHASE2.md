# Phase 2 implementation and verification

4 October 2026. Application implementation is complete; the phase's real-inference and dependency-lock gates remain open. This report contains no recognition-quality or model-speed results.

## Implemented behavior

- Multipart uploads with a measured body ceiling, per-file size limit, bounded file/field counts, UUID paths, preserved originals and input SHA-256.
- WAV preparation with frame validation; other supported formats use a bounded FFmpeg process with network protocols disabled. Original files are never edited.
- One lazy CPU Parakeet v2 INT8 recognizer, four threads by default, bounded non-overlapping windows, stable segment IDs and original audio offsets. Model output strings are preserved exactly. Window offsets are not word timestamps or speaker turns.
- Atomic JSON checkpoints, immutable raw transcript, canonical raw text/JSON exports, byte-range playback and separate `transcribed` state.
- One sequential background worker, three upload/job reservations by default, explicit failure/retry states and interrupted-job recovery. Missing models retain audio and can be retried after setup.
- Setup/doctor/transcribe/retry commands; bounded official model download and safe offline archive installation with provenance and attribution.

## Checks actually run

`python -m unittest discover -s tests -v`: **35 passed**, comprising 10 API, 12 audio/adapter, 4 CLI, 5 contract and 4 archive tests.

Tests exercise rejected/empty/oversized uploads, multipart limits, queue saturation, duplicate retry, responsive health, checkpoint polling, restart recovery, raw immutability, JSON/text parity and audio ranges. Audio checks cover truncated PCM, upload/duration ceilings, conversion arguments/timeouts, full frame coverage without gaps/duplication, silence, missing weights, exact text preservation and global window offsets. Archive tests use artificial contents to test extraction safety, not ONNX validity.

The first API run exposed a Windows `PermissionError` during atomic replacement while a polling reader held `meeting.json` open. Store reads/writes now share a lock. The originally failing tests and a repeated polling regression passed afterward.

A separate Uvicorn server on loopback was exercised through actual HTTP requests with a synthetic sine PCM file, without an ASR substitute:

| Request/outcome | Observed |
| --- | --- |
| Health | 200; transcription prerequisites unavailable |
| Multipart upload | 202; recording accepted |
| Processing | Failed at transcription with explicit missing-Parakeet-files error; retryable |
| Prepared audio byte range | 206; returned bytes matched the uploaded PCM |
| Raw export before transcript exists | 409; no fabricated transcript |
| Interactive API documentation | 200 |

Synthetic PCM is not speech and does not evaluate recognition. Successful transcript-path tests use explicitly labeled `test-double` metadata. The adapter-interface test also uses a recognizer double. No real Parakeet recognition or compressed-audio conversion was executed.

## Test environment and installation boundary

The available interpreter was Python 3.12.14 with Pydantic 2.13.5 and NumPy 2.3.5. Public cached package contents were copied into an ignored local test directory for FastAPI 0.141.1, Starlette 1.7.0, Uvicorn 0.54.0, python-multipart 0.0.32 and HTTPX 0.28.1, plus their cached support packages. Starlette emitted a deprecation warning for its HTTPX test-client compatibility path; the tests passed. These versions are a record of the local checks, not a generated dependency lock.

`uv sync` could not reach PyPI because socket access was denied (`WinError 10013`). The official GitHub model archive was inaccessible for the same reason. sherpa-onnx, imageio-ffmpeg/FFmpeg and the model weights are unavailable in this environment. No successful dependency installation, lockfile, model loading, recognition speed, WER or memory benchmark is claimed.

The API can start while model prerequisites are absent so setup failures are reviewable. `doctor` reports installed runtime/file prerequisites rather than certifying an actual model load. Native inference still has to prove runtime/export compatibility.

## Close the remaining gate

In a network-enabled terminal, from the repository root:

```sh
uv sync
uv run python -m unittest discover -s tests -v
uv run python -m metawispr download-model
uv run python -m metawispr doctor
uv run python -m metawispr transcribe /path/to/shareable-english-meeting.wav --title "ASR smoke"
```

Resolve and commit the resulting `uv.lock`. Preserve the actual `raw.json`, `raw.txt`, model manifest and `meeting.json` from the shareable speech recording. Inspect names, numbers, negation, omissions and window boundaries against the audio; record exact runtime versions and elapsed times. Exercise a genuinely compressed recording through FFmpeg as well. Use an independently provided archive checksum when available; a locally computed hash records identity but does not independently authenticate the download.

Do not run these writes against the same data directory as an active server. Use a shareable recording for published artifacts; private recordings remain ignored. Mark the Phase 2 gate complete only after genuine conversion and recognition succeed. A representative Parakeet/faster-whisper quality comparison belongs to Phase 5.

## Remaining limitations

The application is currently an API/CLI for recorded English audio, with no refinement, documentation or React workspace. No fixed-length window strategy can guarantee an undamaged word boundary; real evaluation must determine whether VAD or another segmentation policy is needed. Offsets support coarse audio seeking only. One process and one inference worker keep local execution bounded; recent-meeting listing scans local metadata and is not a hosted-service database. Code for later LLM stages must consume the immutable raw contract and retain separate provenance.

Implementation references: [official v2 INT8 deployment](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/nemo-transducer-models.html#sherpa-onnx-nemo-parakeet-tdt-0-6b-v2-int8-english), [sherpa-onnx recognizer API](https://github.com/k2-fsa/sherpa-onnx/blob/master/sherpa-onnx/python/sherpa_onnx/offline_recognizer.py), [FFmpeg protocol controls](https://ffmpeg.org/ffmpeg-protocols.html), [FastAPI upload documentation](https://fastapi.tiangolo.com/tutorial/request-files/).
