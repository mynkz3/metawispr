"""Synthetic PCM and explicit test doubles; these are not meeting/model evaluations."""

from io import BytesIO
from pathlib import Path

import numpy as np

from metawispr.audio import file_sha256, inspect_pcm
from metawispr.schemas import ModelInfo, RawTranscript, Segment
import wave


def wav_bytes(seconds=0.25, silent=False, rate=16000, channels=1):
    frames = round(seconds * rate)
    values = np.zeros(frames, dtype="<i2") if silent else (
        np.sin(np.arange(frames) * 2 * np.pi * 440 / rate) * 4000
    ).astype("<i2")
    if channels > 1:
        values = np.repeat(values[:, None], channels, axis=1)
    target = BytesIO()
    with wave.open(target, "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(values.tobytes())
    return target.getvalue()


class FixtureASR:
    """Tests the surrounding workflow, deliberately without invoking any model."""

    def transcribe(self, path, input_hash, created_at, progress=None):
        duration = inspect_pcm(path, 7200)
        if progress:
            progress(duration)
        return RawTranscript(
            input_sha256=input_hash, audio_sha256=file_sha256(path), duration_seconds=duration,
            segments=[Segment(id="s00001", start=0.0, end=duration,
                              text="  Explicit test fixture: do not change 15 to 50.  ")],
            model=ModelInfo(model_id="test-double", package="test-double", runtime="test-double",
                            runtime_version="0", provider="cpu", num_threads=1, file_sha256={}),
            load_seconds=0.0, decode_seconds=0.0, created_at=created_at,
        )
