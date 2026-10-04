"""Bounded audio preparation and the concrete Parakeet ONNX adapter."""

from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
import importlib.util
import os
import shutil
import subprocess
import time
import wave

import numpy as np

from .config import MODEL_FILES, MODEL_ID, MODEL_PACKAGE, InputError, Settings, SetupError
from .schemas import ModelInfo, RawTranscript, Segment


SAMPLE_RATE = 16000


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ffmpeg_executable() -> str:
    explicit = os.getenv("METAWISPR_FFMPEG")
    if explicit:
        if not Path(explicit).is_file():
            raise SetupError("METAWISPR_FFMPEG does not point to an existing executable.")
        return str(Path(explicit).resolve())
    if found := shutil.which("ffmpeg"):
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError) as exc:
        raise SetupError("Install imageio-ffmpeg or set METAWISPR_FFMPEG to your FFmpeg executable.") from exc


def inspect_pcm(path: Path, max_seconds: int) -> float:
    """Validate every frame, without loading an entire meeting into RAM."""
    try:
        with wave.open(str(path), "rb") as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype()) != (1, 2, SAMPLE_RATE, "NONE"):
                raise InputError("Prepared audio must be mono, 16 kHz, 16-bit PCM WAV.")
            frames = source.getnframes()
            duration = frames / SAMPLE_RATE
            if not frames:
                raise InputError("The recording contains no audio frames.")
            if duration > max_seconds:
                raise InputError(f"The recording exceeds the {max_seconds / 60:g}-minute duration limit.")
            remaining = frames
            while remaining:
                count = min(remaining, SAMPLE_RATE * 30)
                block = source.readframes(count)
                if len(block) != count * 2:
                    raise InputError("The WAV recording is truncated or unreadable.")
                remaining -= count
            return duration
    except (wave.Error, EOFError) as exc:
        raise InputError("The recording is not a readable PCM WAV file.") from exc


def prepare_audio(source: Path, destination: Path, settings: Settings) -> float:
    """Convert a working copy; never edit or rename the original upload."""
    if not source.is_file() or source.stat().st_size == 0:
        raise InputError("The recording is empty or missing.")
    if source.stat().st_size > settings.max_upload_bytes:
        raise InputError("The recording exceeds the upload size limit.")
    temporary = destination.with_name("prepared.partial.wav")
    try:
        normalized = False
        try:
            with wave.open(str(source), "rb") as audio:
                normalized = (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getcomptype()) == (1, 2, SAMPLE_RATE, "NONE")
        except (wave.Error, EOFError):
            pass
        if normalized:
            inspect_pcm(source, settings.max_audio_seconds)
            shutil.copyfile(source, temporary)
        else:
            command = [
                ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-xerror",
                "-protocol_whitelist", "file,pipe",
                "-format_whitelist", "wav,mp3,mov,flac,ogg,matroska,webm",
                "-i", str(source.resolve()), "-map", "0:a:0", "-vn", "-sn", "-dn",
                "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le",
                "-t", str(settings.max_audio_seconds + 0.1), str(temporary.resolve()),
            ]
            try:
                result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                        timeout=settings.decode_timeout_seconds, check=False)
            except subprocess.TimeoutExpired as exc:
                raise InputError("Audio conversion timed out. Try a shorter recording or PCM WAV.") from exc
            except OSError as exc:
                raise SetupError("FFmpeg could not be started. Check the configured executable.") from exc
            if result.returncode:
                raise InputError("The recording could not be decoded. Check the file or export it as WAV.")
        duration = inspect_pcm(temporary, settings.max_audio_seconds)
        temporary.replace(destination)
        return duration
    finally:
        temporary.unlink(missing_ok=True)


def audio_windows(path: Path, chunk_seconds: int):
    """Non-overlapping windows, cut near the quietest 200 ms in the last 3 s."""
    if not 1 <= chunk_seconds <= 120:
        raise ValueError("chunk_seconds must be between 1 and 120")
    maximum = chunk_seconds * SAMPLE_RATE
    with wave.open(str(path), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, SAMPLE_RATE):
            raise InputError("Transcription requires prepared mono 16 kHz PCM WAV.")
        total = source.getnframes()
        cursor = 0
        while cursor < total:
            source.setpos(cursor)
            count = min(maximum, total - cursor)
            block = source.readframes(count)
            if len(block) != count * 2:
                raise InputError("Prepared audio is truncated.")
            samples = np.frombuffer(block, dtype="<i2").astype(np.float32) / 32768.0
            cut = len(samples)
            if count == maximum and cursor + count < total and chunk_seconds >= 5:
                step = SAMPLE_RATE // 5
                first = max(step, count - 3 * SAMPLE_RATE)
                starts = range(first, count - step + 1, step)
                quietest = min(starts, key=lambda at: float(np.mean(samples[at:at + step] ** 2)))
                cut = quietest + step // 2
            yield cursor / SAMPLE_RATE, (cursor + cut) / SAMPLE_RATE, samples[:cut]
            cursor += cut


class Parakeet:
    """One lazily loaded recognizer, used by the single inference worker."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.recognizer = None
        self.model_info = None
        self.load_seconds = 0.0

    def load(self):
        if self.recognizer is not None:
            return
        missing = [name for name in MODEL_FILES if not (self.settings.model_dir / name).is_file()]
        if missing:
            raise SetupError("Parakeet files are missing. Run: python -m metawispr download-model")
        try:
            import sherpa_onnx
        except ImportError as exc:
            raise SetupError("Install the sherpa-onnx runtime with uv sync before transcription.") from exc
        started = time.perf_counter()
        try:
            recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=str(self.settings.model_dir / MODEL_FILES[0]),
                decoder=str(self.settings.model_dir / MODEL_FILES[1]),
                joiner=str(self.settings.model_dir / MODEL_FILES[2]),
                tokens=str(self.settings.model_dir / MODEL_FILES[3]),
                num_threads=self.settings.asr_threads, sample_rate=SAMPLE_RATE,
                feature_dim=80, model_type="nemo_transducer", provider="cpu",
                decoding_method="greedy_search",
            )
            info = ModelInfo(
                model_id=MODEL_ID, package=MODEL_PACKAGE, runtime="sherpa-onnx",
                runtime_version=version("sherpa-onnx"), provider="cpu",
                num_threads=self.settings.asr_threads,
                file_sha256={name: file_sha256(self.settings.model_dir / name) for name in MODEL_FILES},
            )
        except Exception as exc:
            raise SetupError("Parakeet could not be loaded. Verify the matching model files and runtime.") from exc
        self.load_seconds = time.perf_counter() - started
        self.model_info, self.recognizer = info, recognizer

    def transcribe(self, path: Path, input_hash: str, created_at: str, progress=None) -> RawTranscript:
        duration = inspect_pcm(path, self.settings.max_audio_seconds)
        segments = []
        decode_seconds = 0.0
        loaded_this_run = self.recognizer is None
        for index, (start, end, samples) in enumerate(audio_windows(path, self.settings.chunk_seconds), 1):
            # Skip only exact digital silence; quiet speech must not be discarded by a guessed threshold.
            if np.any(samples):
                self.load()
                started = time.perf_counter()
                stream = self.recognizer.create_stream()
                stream.accept_waveform(SAMPLE_RATE, samples)
                self.recognizer.decode_stream(stream)
                text = stream.result.text
                decode_seconds += time.perf_counter() - started
                if text.strip():
                    segments.append(Segment(id=f"s{index:05d}", start=start, end=end, text=text))
            if progress:
                progress(end)
        if not segments:
            raise InputError("No speech transcript was produced. Check for silence or unusable audio.")
        return RawTranscript(
            input_sha256=input_hash, audio_sha256=file_sha256(path), duration_seconds=duration,
            segments=segments, model=self.model_info,
            load_seconds=self.load_seconds if loaded_this_run else 0.0,
            decode_seconds=decode_seconds, created_at=created_at,
            warnings=["Timestamps identify audio windows, not individual word boundaries."],
        )


def readiness(settings: Settings) -> dict:
    try:
        ffmpeg_executable()
        conversion_ready = True
    except SetupError:
        conversion_ready = False
    runtime = importlib.util.find_spec("sherpa_onnx") is not None
    missing = [name for name in MODEL_FILES if not (settings.model_dir / name).is_file()]
    return {
        "transcription_ready": runtime and not missing,
        "conversion_ready": conversion_ready,
        "normalized_wav_ready": True,
        "model_id": MODEL_ID,
        "missing_model_files": missing,
        "sherpa_onnx_installed": runtime,
        "setup_commands": ["uv sync", "python -m metawispr download-model"],
    }
