"""Shared persisted and API contracts. Validation of shape is not validation of truth."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


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
    "queued", "preparing", "transcribing", "refining", "documenting", "complete", "failed"
]
