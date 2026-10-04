"""Local settings; relative paths are relative to the process working directory."""

from dataclasses import dataclass
from pathlib import Path
import os


MODEL_ID = "nvidia/parakeet-tdt-0.6b-v2"
MODEL_PACKAGE = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
MODEL_FILES = ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt")
MODEL_URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{MODEL_PACKAGE}.tar.bz2"
SUPPORTED_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm"}


class InputError(ValueError):
    """A recording cannot be processed; submit a different recording."""


class SetupError(RuntimeError):
    """A dependency/model is unavailable; the saved recording can be retried."""


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("data")
    model_dir: Path = Path("models") / MODEL_PACKAGE
    max_upload_bytes: int = 200 * 1024 * 1024
    max_audio_seconds: int = 7200
    asr_threads: int = 4
    chunk_seconds: int = 30
    decode_timeout_seconds: int = 180
    max_pending_jobs: int = 3

    def __post_init__(self):
        for name in ("max_upload_bytes", "max_audio_seconds", "asr_threads", "chunk_seconds",
                     "decode_timeout_seconds", "max_pending_jobs"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not 1 <= self.asr_threads <= 32 or not 1 <= self.chunk_seconds <= 120:
            raise ValueError("ASR threads must be 1–32 and chunk seconds 1–120")

    @classmethod
    def from_env(cls):
        def integer(name, default):
            return int(os.getenv(f"METAWISPR_{name}", str(default)))

        return cls(
            data_dir=Path(os.getenv("METAWISPR_DATA_DIR", "data")).resolve(),
            model_dir=Path(os.getenv("METAWISPR_ASR_DIR", str(Path("models") / MODEL_PACKAGE))).resolve(),
            max_upload_bytes=integer("MAX_UPLOAD_MB", 200) * 1024 * 1024,
            max_audio_seconds=integer("MAX_AUDIO_SECONDS", 7200),
            asr_threads=integer("ASR_THREADS", 4),
            chunk_seconds=integer("CHUNK_SECONDS", 30),
            decode_timeout_seconds=integer("DECODE_TIMEOUT_SECONDS", 180),
            max_pending_jobs=integer("MAX_PENDING_JOBS", 3),
        )
