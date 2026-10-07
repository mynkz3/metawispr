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


class EditProposal(Contract):
    segment_id: str
    original: str = Field(min_length=1)
    replacement: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class EditBatch(Contract):
    edits: list[EditProposal]


class Evidence(Contract):
    segment_id: str
    quote: str = Field(min_length=1)
    start_char: int | None = Field(default=None, ge=0)
    end_char: int | None = Field(default=None, gt=0)


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


class DocumentationBatch(Contract):
    record: MeetingRecord
    revisions: list[Fact]


class ResolvedItem(Contract):
    kind: Literal["decision", "task"]
    text: str = Field(min_length=1)
    owner: str | None
    deadline: str | None
    evidence: list[Evidence] = Field(min_length=1)


class Resolution(Contract):
    candidate_id: str
    disposition: Literal["keep", "retire", "replace", "discard"]
    replacement: ResolvedItem | None
    evidence: list[Evidence] = Field(min_length=1)
    reason: str = Field(min_length=1)


class ResolutionBatch(Contract):
    resolutions: list[Resolution]


class ConsolidatedNotes(Contract):
    summary: list[Fact]
    topics: list[Topic]
    uncertainties: list[str]


class SourceFact(Contract):
    text: str = Field(min_length=1, max_length=300)
    evidence_ids: list[str] = Field(min_length=1)


class SourceTask(SourceFact):
    owner: str | None = Field(description="Exact contiguous text from cited source, or null. Do not complete roles or infer speakers.")
    deadline: str | None = Field(description="Exact contiguous deadline text from cited source, or null. No paraphrase, combined phrases or dates inferred from clocks.")


class SourceTopic(Contract):
    title: str = Field(min_length=1)
    points: list[SourceFact] = Field(min_length=1, max_length=3)


class SourceNotes(Contract):
    summary: list[SourceFact] = Field(max_length=3)
    topics: list[SourceTopic] = Field(max_length=5)
    uncertainties: list[str]


class SelectedTopic(Contract):
    title: str = Field(min_length=1, max_length=80)
    fact_ids: list[str] = Field(min_length=1, max_length=3)


class SelectedNotes(Contract):
    summary_ids: list[str] = Field(max_length=3)
    topics: list[SelectedTopic] = Field(max_length=5)
    uncertainty_ids: list[str] = Field(max_length=8)


class SourceRecord(SourceNotes):
    decisions: list[SourceFact]
    tasks: list[SourceTask]


class SourceBatch(Contract):
    record: SourceRecord
    revisions: list[SourceFact]


class SourceActions(Contract):
    tasks: list[SourceTask]
    decisions: list[SourceFact]
    revisions: list[SourceFact]


class ClaimVerdict(Contract):
    candidate_id: str
    verdict: Literal["supported", "unsupported", "uncertain"]
    evidence_ids: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=240)


class ClaimAudit(Contract):
    verdicts: list[ClaimVerdict]


class SourceItem(SourceTask):
    kind: Literal["decision", "task"]


class SourceResolution(Contract):
    candidate_id: str
    disposition: Literal["keep", "retire", "replace", "discard"]
    replacement: SourceItem | None
    evidence_ids: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=240)


class SourceResolutions(Contract):
    resolutions: list[SourceResolution]


class LLMModel(Contract):
    tag: str
    digest: str = Field(pattern=r"^(sha256:|metadata_sha256:)?[a-f0-9]{64}$")
    runtime_version: str
    parameter_size: str
    quantization: str


class LLMCall(Contract):
    key: str
    model: LLMModel
    prompt_sha256: str
    input_sha256: str
    schema_sha256: str
    context: int
    output_tokens: int
    temperature: float = 0.0
    seed: int = 0
    thinking: bool = False
    thinking_level: str | None = None
    response_model_version: str | None = None
    thought_tokens: int | None = Field(default=None, ge=0)
    presence_penalty: float | None = None
    repeat_penalty: float | None = None
    elapsed_seconds: float = Field(ge=0)
    prompt_tokens: int | None = Field(ge=0)
    generated_tokens: int | None = Field(ge=0)
    attempts: int = Field(ge=1, le=2)


class RejectedEdit(Contract):
    edit: Edit | EditProposal
    rejection: str


class RefinedTranscript(Contract):
    schema_version: Literal["1.0"] = "1.0"
    source_sha256: str
    policy_sha256: str
    created_at: str
    segments: list[Segment] = Field(min_length=1)
    accepted: list[Edit]
    rejected: list[RejectedEdit]
    calls: list[LLMCall] = Field(min_length=1)
    warnings: list[str]


class DocumentedMeeting(Contract):
    schema_version: Literal["1.0"] = "1.0"
    source_sha256: str
    policy_sha256: str
    created_at: str
    record: MeetingRecord
    revision_audit: list[Fact] = Field(default_factory=list)
    calls: list[LLMCall] = Field(min_length=1)
    warnings: list[str]


Stage = Literal[
    "queued", "preparing", "transcribing", "transcribed", "refining", "documenting", "complete", "failed"
]


class ModelInfo(Contract):
    model_id: str
    package: str
    runtime: str
    runtime_version: str
    provider: Literal["cpu", "cuda"]
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
    target: Literal["transcribed", "complete"] = "complete"
    llm_completed_calls: int = Field(default=0, ge=0)
    refined_at: str | None = None
    documented_at: str | None = None


class MeetingView(Contract):
    meeting: Meeting
    raw: RawTranscript | None
    refined: RefinedTranscript | None = None
    document: DocumentedMeeting | None = None
