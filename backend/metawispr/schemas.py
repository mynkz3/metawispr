"""Shared persisted and API contracts. Validation of shape is not validation of truth."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Segment(Contract):
    id: str = Field(min_length=1)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def ordered_times(self):
        if self.end <= self.start:
            raise ValueError("segment end must follow start")
        return self


class Edit(Contract):
    segment_id: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    original: str = Field(min_length=1)
    replacement: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class EditBatch(Contract):
    edits: list[Edit]


class Evidence(Contract):
    segment_id: str
    quote: str = Field(min_length=1)


class Fact(Contract):
    text: str = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)


class Topic(Contract):
    title: str = Field(min_length=1)
    points: list[Fact] = Field(min_length=1)


class Task(Fact):
    owner: str | None
    deadline: str | None


class MeetingRecord(Contract):
    summary: list[Fact]
    topics: list[Topic]
    decisions: list[Fact]
    tasks: list[Task]
    uncertainties: list[str]


Stage = Literal[
    "queued", "preparing", "transcribing", "transcribed", "refining", "documenting", "complete", "failed"
]


class ModelInfo(Contract):
    model_id: str
    package: str
    runtime: str
    runtime_version: str
    provider: Literal["cpu"]
    num_threads: int = Field(ge=1)
    file_sha256: dict[str, str]


class RawTranscript(Contract):
    schema_version: Literal["1.0"] = "1.0"
    input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    audio_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    duration_seconds: float = Field(gt=0)
    timing: Literal["audio_window"] = "audio_window"
    segments: list[Segment] = Field(min_length=1)
    model: ModelInfo
    load_seconds: float = Field(ge=0)
    decode_seconds: float = Field(ge=0)
    created_at: str
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_segment_timeline(self):
        previous_end = 0.0
        identifiers = set()
        for segment in self.segments:
            if segment.id in identifiers:
                raise ValueError("segment IDs must be unique")
            if segment.start < previous_end or segment.end > self.duration_seconds + 0.0001:
                raise ValueError("segments must be ordered within the audio duration")
            identifiers.add(segment.id)
            previous_end = segment.end
        return self


class Meeting(Contract):
    id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    title: str = Field(min_length=1, max_length=200)
    filename: str
    source_name: str
    glossary: str = Field(max_length=10000)
    created_at: str
    updated_at: str
    stage: Stage
    input_sha256: str | None = None
    size_bytes: int = Field(default=0, ge=0)
    duration_seconds: float | None = Field(default=None, gt=0)
    processed_audio_seconds: float = Field(default=0.0, ge=0)
    prepare_seconds: float | None = Field(default=None, ge=0)
    transcribed_at: str | None = None
    failed_stage: Stage | None = None
    error: str | None = None
    retryable: bool = False


class MeetingView(Contract):
    meeting: Meeting
    raw: RawTranscript | None
