"""Request and response models for the HTTP API."""

import datetime as dt
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def _as_utc(value: dt.datetime) -> dt.datetime:
    return value.replace(tzinfo=dt.UTC) if value.tzinfo is None else value


# SQLite drops the timezone, but every stored time is UTC (models.utcnow).
# Marking it keeps clients from reading the times as local.
UtcDatetime = Annotated[dt.datetime, AfterValidator(_as_utc)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Documents and versions -------------------------------------------------


class QueuedUpload(BaseModel):
    job_id: int
    filename: str


class UploadResponse(BaseModel):
    jobs: list[QueuedUpload]


class DocumentOut(BaseModel):
    id: int
    collection_id: int
    filename: str
    tags: list[str]
    active_version_id: int | None
    active_version_number: int | None
    version_count: int
    trashed_at: UtcDatetime | None
    created_at: UtcDatetime


class VersionOut(BaseModel):
    id: int
    version_number: int
    sha256: str
    ext: str
    note: str | None
    is_active: bool
    chunk_count: int
    created_at: UtcDatetime


class DiffOut(BaseModel):
    a: int
    b: int
    diff: list[str]


class RollbackIn(BaseModel):
    version_id: int


# --- Collections --------------------------------------------------------------


class CollectionIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"name": "papers"}]})

    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    embedding_model: str | None = None
    chunk_size_tokens: int | None = Field(default=None, ge=50, le=4000)
    chunk_overlap_pct: float | None = Field(default=None, ge=0.0, lt=0.5)


class CollectionReindexIn(BaseModel):
    """Leave everything empty for an in-place reindex. Any change of model or
    chunking triggers a blue/green rebuild into a new generation."""

    model_config = ConfigDict(json_schema_extra={"examples": [{}]})

    embedding_model: str | None = None
    chunk_size_tokens: int | None = Field(default=None, ge=50, le=4000)
    chunk_overlap_pct: float | None = Field(default=None, ge=0.0, lt=0.5)


class CollectionOut(ORMModel):
    id: int
    name: str
    chroma_collection: str
    embedding_model: str
    chunk_size_tokens: int
    chunk_overlap_pct: float
    is_active: bool
    created_at: UtcDatetime
    document_count: int = 0


class JobQueued(BaseModel):
    job_id: int
    mode: str | None = None  # collections: "in_place" | "blue_green"
    target_collection_id: int | None = None


# --- Jobs ---------------------------------------------------------------------


class JobOut(BaseModel):
    id: int
    job_type: str
    status: str
    progress: float
    error: str | None
    result: dict[str, Any] | None
    retries: int
    cancel_requested: bool
    document_id: int | None
    payload: dict[str, Any]
    subject: str | None = None  # what the job is about: a file name or "shelf <name>"
    note: str | None = None  # plain-language outcome, e.g. why an upload was skipped
    created_at: UtcDatetime
    updated_at: UtcDatetime


# --- Retrieval and chat -------------------------------------------------------


class RetrieveIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"question": "What does the document say about X?"}]}
    )

    question: str = Field(min_length=1, max_length=4000)
    collection_id: int | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)


class ChunkOut(BaseModel):
    rank: int
    chunk_id: int
    document_id: int
    version_id: int | None
    filename: str
    page: int | None
    heading: str | None
    score: float
    text: str


class RetrieveOut(BaseModel):
    collection_id: int
    chunks: list[ChunkOut]


class ChatIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"question": "What does the document say about X?"}]}
    )

    question: str = Field(min_length=1, max_length=4000)
    session_id: int | None = None
    collection_id: int | None = None
    profile: str | None = None  # profile name; defaults to "default"


class ChunkDetail(BaseModel):
    """One passage, for showing what a citation points at."""

    id: int
    text: str
    document_id: int
    filename: str
    collection_id: int
    version_id: int
    version_number: int
    page: int | None
    heading: str | None
    retired: bool  # replaced by a reindex; kept because an answer cites it


class SessionSummary(BaseModel):
    id: int
    title: str
    created_at: UtcDatetime
    message_count: int
    collection_id: int | None = None


class SourceOut(BaseModel):
    rank: int
    chunk_id: int
    score: float
    document_id: int | None
    filename: str | None
    page: int | None
    heading: str | None


class FeedbackIn(BaseModel):
    thumbs_up: bool
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackOut(ORMModel):
    message_id: int
    thumbs_up: bool
    comment: str | None
    created_at: UtcDatetime


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    rag_profile_id: int | None
    created_at: UtcDatetime
    sources: list[SourceOut]
    feedback: FeedbackOut | None
    # Assistant messages: ok / missing / invalid / not_applicable (retrieval.citations)
    citation_status: str | None = None


class SessionOut(BaseModel):
    id: int
    title: str
    created_at: UtcDatetime
    collection_id: int | None = None
    messages: list[MessageOut]


# --- Models and profiles ------------------------------------------------------


class ModelOut(BaseModel):
    name: str
    size: int | None = None
    modified_at: str | None = None
    family: str | None = None
    parameter_size: str | None = None
    capabilities: list[str] = []  # from Ollama, e.g. ["embedding"] or ["completion"]


class ModelPullIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProfileIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"name": "default", "retrieval_top_k": 8}]}
    )

    name: str = Field(default="default", min_length=1, max_length=64)
    chat_model: str | None = None
    embedding_model: str | None = None
    chunk_size_tokens: int | None = None
    chunk_overlap_pct: float | None = None
    retrieval_top_k: int | None = None
    temperature: float | None = None
    system_prompt: str | None = None


class ProfileOut(ORMModel):
    id: int
    name: str
    version: int
    chat_model: str
    embedding_model: str
    chunk_size_tokens: int
    chunk_overlap_pct: float
    retrieval_top_k: int
    temperature: float
    system_prompt: str
    is_active: bool
    created_at: UtcDatetime


# --- Ops ----------------------------------------------------------------------


class AuditOut(ORMModel):
    id: int
    action: str
    entity_type: str
    entity_id: int | None
    detail: str
    created_at: UtcDatetime


class ComponentHealth(BaseModel):
    ok: bool
    detail: str | None = None


class DiagnosticAction(BaseModel):
    kind: str  # pull_model | reindex_collection | open_queue | open_collections
    label: str
    target: str | None = None


class DiagnosticCheck(BaseModel):
    id: str
    component: str  # ollama | sqlite | vector_store | jobs
    title: str
    status: str  # ok | warn | fail | skip
    detail: str
    cause: str | None = None
    fix: str | None = None
    commands: list[str] = []
    action: DiagnosticAction | None = None


class DiagnosticsOut(BaseModel):
    status: str  # ok | warn | fail
    checks: list[DiagnosticCheck]
    simulated: list[str]  # SIMULATE_FAULTS in effect (developer setting)
    ran_at: UtcDatetime


class SupportDraftOut(BaseModel):
    """A prefilled service-desk incident, for the user to review."""

    environment: dict[str, Any]  # computer, user, OS, versions, models
    category: str
    subcategory: str
    assignment_group: str
    impact: int  # 1 high .. 3 low
    urgency: int  # 1 high .. 3 low
    priority: str  # from the impact/urgency matrix, e.g. "2 - High"
    short_description: str
    system_status: str  # troubleshooter: ok | warn | fail
    problems: list[dict[str, Any]]
    simulated_faults: list[str]


class SupportTicketIn(BaseModel):
    caller_name: str = Field(min_length=1, max_length=120)
    contact: str | None = Field(default=None, max_length=200)
    best_time_to_contact: str | None = Field(default=None, max_length=200)
    impact: int = Field(ge=1, le=3)
    urgency: int = Field(ge=1, le=3)
    short_description: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=4000)  # "what happened"
    started_at: str | None = Field(default=None, max_length=100)
    recent_changes: str | None = Field(default=None, max_length=1000)
    users_affected: str | None = Field(default=None, max_length=200)
    steps_to_reproduce: str | None = Field(default=None, max_length=2000)


class SupportTicketOut(BaseModel):
    number: str  # e.g. INC0010001
    saved_to: str  # simulated: the incident is saved locally, never sent
    incident: dict[str, Any]


class HealthOut(BaseModel):
    status: str  # "ok" | "degraded" | "down"
    simulated: list[str] = []
    ollama: ComponentHealth
    sqlite: ComponentHealth
    vector_store: ComponentHealth
    job_worker: ComponentHealth
