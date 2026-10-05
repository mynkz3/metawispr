"""Synthetic PCM and explicit test doubles; these are not meeting/model evaluations."""

from io import BytesIO
from pathlib import Path

import numpy as np

from metawispr.audio import file_sha256, inspect_pcm
from metawispr.schemas import ModelInfo, RawTranscript, Segment
import wave
import json

from metawispr.llm import Ollama
from metawispr.schemas import LLMModel


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


class FixtureLLM(Ollama):
    """Exercises the real adapter/checkpoint code with explicitly fabricated responses."""

    def __init__(self, settings):
        super().__init__(settings)
        self.requests = []
        self.unloaded = []
        self.fail_document = False

    def models(self):
        return tuple(LLMModel(tag=tag, digest=character * 64, runtime_version="test-double",
                              parameter_size="test-double", quantization="test-double")
                     for tag, character in ((self.settings.refiner_model, "a"),
                                            (self.settings.documenter_model,
                                             "a" if self.settings.documenter_model == self.settings.refiner_model else "b")))

    def request(self, method, path, body=None, timeout=None):
        from metawispr.config import SetupError
        self.requests.append((path, body))
        refining = "edits" in body["format"]["properties"]
        if self.fail_document and not refining:
            raise SetupError("Explicit test-double documentation failure")
        payload = json.loads(body["messages"][1]["content"])
        if refining:
            output = {"edits": []}
        else:
            record = {"summary": [], "topics": [], "decisions": [], "tasks": [], "uncertainties": []}
            if "segments" in payload:
                segment = payload["segments"][0]
                record["summary"] = [{"text": "Explicit test-double summary", "evidence_ids": [segment["id"]]}]
            else:
                for batch in payload["chronological_batches"]:
                    for fact in batch["record"]["summary"]:
                        record["summary"].append(fact)
            properties = body["format"]["properties"]
            output = ({"decisions": record["decisions"], "tasks": record["tasks"], "revisions": []}
                      if "decisions" in properties else
                      {key: record[key] for key in ("summary", "topics", "uncertainties")})
        return {"done": True, "done_reason": "stop", "message": {"content": json.dumps(output)},
                "prompt_eval_count": 1, "eval_count": 1}

    def unload(self, model):
        self.unloaded.append(model.tag)
