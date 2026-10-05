"""Local settings; relative paths are relative to the process working directory."""

from dataclasses import dataclass
from pathlib import Path
import os
from urllib.parse import urlsplit


MODEL_ID = "nvidia/parakeet-tdt-0.6b-v2"
MODEL_PACKAGE = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
MODEL_FILES = ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt")
MODEL_URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{MODEL_PACKAGE}.tar.bz2"
ASR_VARIANTS = {
    "int8": (MODEL_PACKAGE, MODEL_FILES),
    "fp16": ("sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-fp16",
             ("encoder.fp16.onnx", "decoder.fp16.onnx", "joiner.fp16.onnx", "tokens.txt")),
}
SUPPORTED_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm"}


class InputError(ValueError):
    """A recording cannot be processed; submit a different recording."""


class SetupError(RuntimeError):
    """A dependency/model is unavailable; the saved recording can be retried."""


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("data")
    ui_dir: Path = Path("frontend/dist")
    model_dir: Path = Path("models") / MODEL_PACKAGE
    max_upload_bytes: int = 200 * 1024 * 1024
    max_audio_seconds: int = 7200
    asr_threads: int = 4
    asr_provider: str = "cpu"
    asr_precision: str = "int8"
    chunk_seconds: int = 30
    decode_timeout_seconds: int = 180
    max_pending_jobs: int = 3
    ollama_url: str = "http://127.0.0.1:11434"
    refiner_model: str = "qwen3.5:4b"
    documenter_model: str = "qwen3.5:4b"
    llm_context: int = 16384
    llm_output_tokens: int = 3072
    llm_timeout_seconds: int = 300

    def __post_init__(self):
        for name in ("max_upload_bytes", "max_audio_seconds", "asr_threads", "chunk_seconds",
                     "decode_timeout_seconds", "max_pending_jobs", "llm_context",
                     "llm_output_tokens", "llm_timeout_seconds"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not 1 <= self.asr_threads <= 32 or not 1 <= self.chunk_seconds <= 120:
            raise ValueError("ASR threads must be 1–32 and chunk seconds 1–120")
        if self.asr_provider not in {"cpu", "cuda"} or self.asr_precision not in ASR_VARIANTS:
            raise ValueError("ASR provider must be cpu/cuda and precision must be int8/fp16")
        if self.llm_context < 4096 or self.llm_output_tokens >= self.llm_context // 2:
            raise ValueError("LLM context must be at least 4096; output must be less than half the context")
        endpoint = urlsplit(self.ollama_url)
        if (endpoint.scheme != "http" or endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}
                or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment
                or endpoint.path not in {"", "/"}):
            raise ValueError("Ollama must use a local HTTP endpoint, without credentials or a path")
        if not self.refiner_model.strip() or not self.documenter_model.strip():
            raise ValueError("Refinement and documentation require nonempty installed model tags")

    @classmethod
    def from_env(cls):
        def integer(name, default):
            return int(os.getenv(f"METAWISPR_{name}", str(default)))

        precision = os.getenv("METAWISPR_ASR_PRECISION", "int8")
        if precision not in ASR_VARIANTS:
            raise ValueError("ASR precision must be int8 or fp16")
        return cls(
            data_dir=Path(os.getenv("METAWISPR_DATA_DIR", "data")).resolve(),
            ui_dir=Path(os.getenv("METAWISPR_UI_DIR", "frontend/dist")).resolve(),
            model_dir=Path(os.getenv("METAWISPR_ASR_DIR", str(Path("models") / ASR_VARIANTS[precision][0]))).resolve(),
            max_upload_bytes=integer("MAX_UPLOAD_MB", 200) * 1024 * 1024,
            max_audio_seconds=integer("MAX_AUDIO_SECONDS", 7200),
            asr_threads=integer("ASR_THREADS", 4),
            asr_provider=os.getenv("METAWISPR_ASR_PROVIDER", "cpu"),
            asr_precision=precision,
            chunk_seconds=integer("CHUNK_SECONDS", 30),
            decode_timeout_seconds=integer("DECODE_TIMEOUT_SECONDS", 180),
            max_pending_jobs=integer("MAX_PENDING_JOBS", 3),
            ollama_url=os.getenv("METAWISPR_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
            refiner_model=os.getenv("METAWISPR_REFINER_MODEL", "qwen3.5:4b"),
            documenter_model=os.getenv("METAWISPR_DOCUMENTER_MODEL", "qwen3.5:4b"),
            llm_context=integer("LLM_CONTEXT", 16384),
            llm_output_tokens=integer("LLM_OUTPUT_TOKENS", 3072),
            llm_timeout_seconds=integer("LLM_TIMEOUT_SECONDS", 300),
        )
