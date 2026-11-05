"""SQLAlchemy models for all tables (PLAN.md section 4).

Supersedes app/ingest/sqlite_store.py's Phase 1 raw-sqlite3 subset, which
only ever covered `documents` and `chunks`. Versioning lives on top of
these models in app/versioning/service.py, the single service layer that
writes to them (CLAUDE.md invariant 1).
"""

import datetime as dt

from sqlalchemy import Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Collection(Base):
    """A knowledge base: an embedding model + chunking config pinned to a
    specific Chroma collection. Blue/green swaps (invariant 4) create a new
    row with a new `chroma_collection` name and deactivate the old one."""

    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(index=True)
    chroma_collection: Mapped[str] = mapped_column(unique=True)
    embedding_model: Mapped[str]
    chunk_size_tokens: Mapped[int] = mapped_column(default=600)
    chunk_overlap_pct: Mapped[float] = mapped_column(default=0.12)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)

    documents: Mapped[list["Document"]] = relationship(back_populates="collection")


class Document(Base):
    """A logical file. `active_version_id` is a plain column (no DB-level
    FK, to avoid a circular FK with document_versions) pointed at by
    rollback without touching anything else (invariant 3)."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"), index=True)
    filename: Mapped[str] = mapped_column(index=True)
    tags: Mapped[str] = mapped_column(default="")
    active_version_id: Mapped[int | None] = mapped_column(Integer, default=None)
    trashed_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)

    collection: Mapped["Collection"] = relationship(back_populates="documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(back_populates="document")


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    version_number: Mapped[int]
    sha256: Mapped[str] = mapped_column(unique=True, index=True)
    original_path: Mapped[str]
    ext: Mapped[str]
    extracted_text: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)

    document: Mapped["Document"] = relationship(back_populates="versions")
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="version")


class Chunk(Base):
    """One chunk of one version, as indexed into one collection. A blue/green
    rebuild re-chunks every version into the new collection, so the same
    version can have chunks in two collections until the old one is purged."""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id"), index=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"), index=True)
    chunk_index: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(default=None)
    heading: Mapped[str | None] = mapped_column(default=None)
    token_estimate: Mapped[int]

    version: Mapped["DocumentVersion"] = relationship(back_populates="chunks")


class IngestJob(Base):
    """SQLite-backed job queue row (no Redis). One in-process worker polls
    for `pending` jobs; `status` transitions: pending -> running ->
    completed|failed|cancelled. Retry resets a failed job back to pending."""

    __tablename__ = "ingest_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str]
    status: Mapped[str] = mapped_column(default="pending", index=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    progress: Mapped[float] = mapped_column(default=0.0)
    error: Mapped[str | None] = mapped_column(default=None)
    result: Mapped[str | None] = mapped_column(Text, default=None)
    retries: Mapped[int] = mapped_column(default=0)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    document_id: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(default=utcnow)


class RagProfile(Base):
    """A versioned settings snapshot. Every assistant message records the
    profile version it used (invariant 5)."""

    __tablename__ = "rag_profiles"
    __table_args__ = (UniqueConstraint("name", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(index=True)
    version: Mapped[int]
    chat_model: Mapped[str]
    embedding_model: Mapped[str]
    chunk_size_tokens: Mapped[int]
    chunk_overlap_pct: Mapped[float]
    retrieval_top_k: Mapped[int]
    temperature: Mapped[float]
    system_prompt: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(default="New chat")
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)

    messages: Mapped[list["Message"]] = relationship(back_populates="session")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str]
    content: Mapped[str] = mapped_column(Text)
    rag_profile_id: Mapped[int | None] = mapped_column(ForeignKey("rag_profiles.id"), default=None)
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
    sources: Mapped[list["MessageSource"]] = relationship(back_populates="message")
    feedback_entries: Mapped[list["Feedback"]] = relationship(back_populates="message")


class MessageSource(Base):
    """Retrieved chunks + scores behind one assistant message (invariant 5)."""

    __tablename__ = "message_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), index=True)
    chunk_id: Mapped[int] = mapped_column(ForeignKey("chunks.id"))
    rank: Mapped[int]
    score: Mapped[float] = mapped_column(Float)

    message: Mapped["Message"] = relationship(back_populates="sources")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), unique=True)
    thumbs_up: Mapped[bool]
    comment: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)

    message: Mapped["Message"] = relationship(back_populates="feedback_entries")


class EvalSet(Base):
    __tablename__ = "eval_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)

    cases: Mapped[list["EvalCase"]] = relationship(back_populates="eval_set")


class EvalCase(Base):
    __tablename__ = "eval_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    eval_set_id: Mapped[int] = mapped_column(ForeignKey("eval_sets.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    expected_source: Mapped[str | None] = mapped_column(default=None)
    expected_answer_notes: Mapped[str | None] = mapped_column(Text, default=None)

    eval_set: Mapped["EvalSet"] = relationship(back_populates="cases")


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    eval_set_id: Mapped[int] = mapped_column(ForeignKey("eval_sets.id"), index=True)
    rag_profile_id: Mapped[int | None] = mapped_column(ForeignKey("rag_profiles.id"), default=None)
    hit_rate_at_5: Mapped[float | None] = mapped_column(default=None)
    mrr: Mapped[float | None] = mapped_column(default=None)
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow)


class AuditLog(Base):
    """Every upload, delete, rollback, reindex, and settings change
    (invariant 7)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(index=True)
    entity_type: Mapped[str]
    entity_id: Mapped[int | None] = mapped_column(default=None)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(default=utcnow, index=True)
