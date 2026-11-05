"""The versioning service layer (CLAUDE.md invariant 1).

All writes to SQLite, Chroma, and the file store go through this module
(plus app/ingest's pure parsing/chunking/file-store helpers, which this
module calls into). Routes and the CLI never write directly.

Implements CLAUDE.md invariants 2-4 and 7, and PLAN.md section 5:
content-addressed files, duplicate-by-hash skip, new-version-on-change,
rollback-by-pointer-flip (no re-embedding), soft delete with trash, and
blue/green collection swaps on embedding/chunking changes.
"""

import datetime as dt
import difflib
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import fts
from app.db.models import AuditLog, Chunk, Collection, Document, DocumentVersion, utcnow
from app.ingest import file_store
from app.ingest.chunker import chunk_blocks
from app.ingest.parsers import parse_file
from app.llm.base import EmbeddingClient
from app.retrieval.vector_store import VectorStore

DEFAULT_COLLECTION_NAME = "default"
DEFAULT_TRASH_DAYS = 30


@dataclass
class IngestResult:
    status: str  # "ingested" | "skipped_duplicate"
    document_id: int
    version_id: int | None = None
    chunk_count: int = 0


def _audit(
    db: Session, action: str, entity_type: str, entity_id: int | None, detail: str = ""
) -> None:
    db.add(AuditLog(action=action, entity_type=entity_type, entity_id=entity_id, detail=detail))


# --- Collections (invariant 4: embedding model per collection, blue/green) --


def get_active_collection(db: Session, name: str) -> Collection | None:
    return db.execute(
        select(Collection).where(Collection.name == name, Collection.is_active.is_(True))
    ).scalar_one_or_none()


def create_collection(
    db: Session,
    vector_store: VectorStore,
    *,
    name: str,
    embedding_model: str,
    chunk_size_tokens: int = 600,
    chunk_overlap_pct: float = 0.12,
) -> Collection:
    """Creates a collection. If one with this name is already active (e.g.
    the embedding model or chunking changed), this is a blue/green swap:
    the old row is deactivated but kept until documents are reindexed into
    the new one."""
    existing_active = get_active_collection(db, name)
    generation = 1
    if existing_active is not None:
        generation = _next_generation(db, name)
        existing_active.is_active = False

    chroma_collection = f"{name}__g{generation}"
    collection = Collection(
        name=name,
        chroma_collection=chroma_collection,
        embedding_model=embedding_model,
        chunk_size_tokens=chunk_size_tokens,
        chunk_overlap_pct=chunk_overlap_pct,
        is_active=True,
    )
    db.add(collection)
    db.flush()

    vector_store.get_or_create_collection(
        chroma_collection,
        metadata={
            "embedding_model": embedding_model,
            "chunk_size_tokens": chunk_size_tokens,
            "chunk_overlap_pct": chunk_overlap_pct,
        },
    )

    if existing_active is not None:
        detail = (
            f"blue/green swap from collection {existing_active.id} "
            f"({existing_active.chroma_collection})"
        )
        _audit(db, "collection_swap", "collection", collection.id, detail)
    else:
        _audit(db, "collection_create", "collection", collection.id, chroma_collection)

    db.commit()
    return collection


def _next_generation(db: Session, name: str) -> int:
    count = db.execute(select(Collection).where(Collection.name == name)).scalars().all()
    return len(count) + 1


def get_or_create_default_collection(
    db: Session, vector_store: VectorStore, settings: Settings
) -> Collection:
    existing = get_active_collection(db, DEFAULT_COLLECTION_NAME)
    if existing is not None:
        return existing
    return create_collection(
        db,
        vector_store,
        name=DEFAULT_COLLECTION_NAME,
        embedding_model=settings.embedding_model,
        chunk_size_tokens=settings.chunk_size_tokens,
        chunk_overlap_pct=settings.chunk_overlap_pct,
    )


# --- Ingestion (invariants 2, 3) -------------------------------------------


def ingest_document(
    db: Session,
    *,
    collection: Collection,
    source_path: Path,
    settings: Settings,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
) -> IngestResult:
    sha256 = file_store.hash_file(source_path)

    existing_version = db.execute(
        select(DocumentVersion).where(DocumentVersion.sha256 == sha256)
    ).scalar_one_or_none()
    if existing_version is not None:
        return IngestResult(
            status="skipped_duplicate",
            document_id=existing_version.document_id,
            version_id=existing_version.id,
        )

    file_store.store_file(source_path, settings.files_dir)

    document = db.execute(
        select(Document).where(
            Document.collection_id == collection.id,
            Document.filename == source_path.name,
            Document.trashed_at.is_(None),
        )
    ).scalar_one_or_none()
    if document is None:
        document = Document(collection_id=collection.id, filename=source_path.name)
        db.add(document)
        db.flush()

    version_number = _next_version_number(db, document.id)

    parsed = parse_file(
        source_path,
        ocr_lang=settings.ocr_lang,
        ocr_min_text_chars=settings.ocr_min_text_chars,
        tesseract_cmd=settings.tesseract_cmd,
        tessdata_prefix=settings.tessdata_prefix,
    )
    chunks = chunk_blocks(
        parsed.blocks,
        chunk_size_tokens=collection.chunk_size_tokens,
        overlap_pct=collection.chunk_overlap_pct,
    )

    version = DocumentVersion(
        document_id=document.id,
        version_number=version_number,
        sha256=sha256,
        original_path=str(source_path),
        ext=source_path.suffix.lower(),
        extracted_text=parsed.full_text,
    )
    db.add(version)
    db.flush()

    chunk_rows = [
        Chunk(
            version_id=version.id,
            chunk_index=i,
            text=c.text,
            page=c.page,
            heading=c.heading,
            token_estimate=c.token_estimate,
        )
        for i, c in enumerate(chunks)
    ]
    db.add_all(chunk_rows)
    db.flush()

    for row in chunk_rows:
        fts.index_chunk(db, row.id, row.text)

    if chunk_rows:
        embeddings = embedding_client.embed([row.text for row in chunk_rows])
        vector_store.upsert(
            collection.chroma_collection,
            ids=[f"{version.id}:{row.id}" for row in chunk_rows],
            embeddings=embeddings,
            metadatas=[
                {
                    "document_id": document.id,
                    "version_id": version.id,
                    "filename": document.filename,
                    "chunk_index": row.chunk_index,
                    "page": row.page or 0,
                    "heading": row.heading or "",
                }
                for row in chunk_rows
            ],
            documents=[row.text for row in chunk_rows],
        )

    document.active_version_id = version.id
    _audit(db, "upload", "document", document.id, f"version {version_number}")
    db.commit()

    return IngestResult(
        status="ingested",
        document_id=document.id,
        version_id=version.id,
        chunk_count=len(chunk_rows),
    )


def _next_version_number(db: Session, document_id: int) -> int:
    existing = (
        db.execute(
            select(DocumentVersion.version_number).where(DocumentVersion.document_id == document_id)
        )
        .scalars()
        .all()
    )
    return (max(existing) if existing else 0) + 1


# --- Rollback (invariant 3: pointer flip only, no re-embedding) -----------


def rollback_document(db: Session, document_id: int, version_id: int) -> DocumentVersion:
    document = db.get(Document, document_id)
    if document is None:
        raise ValueError(f"document {document_id} not found")
    version = db.get(DocumentVersion, version_id)
    if version is None or version.document_id != document_id:
        raise ValueError(f"version {version_id} does not belong to document {document_id}")

    document.active_version_id = version.id
    _audit(db, "rollback", "document", document.id, f"to version {version.version_number}")
    db.commit()
    return version


# --- Soft delete / trash (invariant 3) -------------------------------------


def soft_delete_document(db: Session, document_id: int) -> None:
    document = db.get(Document, document_id)
    if document is None:
        raise ValueError(f"document {document_id} not found")
    document.trashed_at = utcnow()
    _audit(db, "delete", "document", document.id, "soft delete")
    db.commit()


def restore_document(db: Session, document_id: int) -> None:
    document = db.get(Document, document_id)
    if document is None:
        raise ValueError(f"document {document_id} not found")
    document.trashed_at = None
    _audit(db, "restore", "document", document.id, "")
    db.commit()


def purge_expired_trash(
    db: Session, vector_store: VectorStore, *, older_than_days: int = DEFAULT_TRASH_DAYS
) -> list[int]:
    """Hard-deletes documents trashed more than `older_than_days` ago.
    Returns the purged document ids."""
    cutoff = utcnow() - dt.timedelta(days=older_than_days)
    documents = (
        db.execute(
            select(Document).where(Document.trashed_at.isnot(None), Document.trashed_at < cutoff)
        )
        .scalars()
        .all()
    )

    purged_ids = []
    for document in documents:
        collection = db.get(Collection, document.collection_id)
        versions = (
            db.execute(select(DocumentVersion).where(DocumentVersion.document_id == document.id))
            .scalars()
            .all()
        )
        for version in versions:
            chunks = db.execute(select(Chunk).where(Chunk.version_id == version.id)).scalars().all()
            if chunks:
                vector_store.delete(
                    collection.chroma_collection, [f"{version.id}:{c.id}" for c in chunks]
                )
                for chunk in chunks:
                    fts.remove_chunk(db, chunk.id, chunk.text)
                    db.delete(chunk)
            db.delete(version)
        purged_ids.append(document.id)
        db.delete(document)
        _audit(db, "purge", "document", document.id, f"{len(versions)} version(s)")

    db.commit()
    return purged_ids


# --- Diff (PLAN.md section 5) ----------------------------------------------


def diff_versions(db: Session, version_a_id: int, version_b_id: int) -> list[str]:
    version_a = db.get(DocumentVersion, version_a_id)
    version_b = db.get(DocumentVersion, version_b_id)
    if version_a is None or version_b is None:
        raise ValueError("one or both versions not found")

    return list(
        difflib.unified_diff(
            version_a.extracted_text.splitlines(),
            version_b.extracted_text.splitlines(),
            fromfile=f"v{version_a.version_number}",
            tofile=f"v{version_b.version_number}",
            lineterm="",
        )
    )


# --- Reindex (realizes a blue/green swap for already-ingested documents) --


def reindex_document(
    db: Session,
    document_id: int,
    *,
    settings: Settings,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
) -> IngestResult:
    document = db.get(Document, document_id)
    if document is None or document.active_version_id is None:
        raise ValueError(f"document {document_id} has no active version to reindex")
    collection = db.get(Collection, document.collection_id)
    active_version = db.get(DocumentVersion, document.active_version_id)

    source_path = file_store.files_path_for(
        settings.files_dir, active_version.sha256, active_version.ext
    )

    old_chunks = (
        db.execute(select(Chunk).where(Chunk.version_id == active_version.id)).scalars().all()
    )
    if old_chunks:
        vector_store.delete(
            collection.chroma_collection, [f"{active_version.id}:{c.id}" for c in old_chunks]
        )
        for chunk in old_chunks:
            fts.remove_chunk(db, chunk.id, chunk.text)
            db.delete(chunk)
    db.flush()

    parsed = parse_file(
        source_path,
        ocr_lang=settings.ocr_lang,
        ocr_min_text_chars=settings.ocr_min_text_chars,
        tesseract_cmd=settings.tesseract_cmd,
        tessdata_prefix=settings.tessdata_prefix,
    )
    chunks = chunk_blocks(
        parsed.blocks,
        chunk_size_tokens=collection.chunk_size_tokens,
        overlap_pct=collection.chunk_overlap_pct,
    )

    chunk_rows = [
        Chunk(
            version_id=active_version.id,
            chunk_index=i,
            text=c.text,
            page=c.page,
            heading=c.heading,
            token_estimate=c.token_estimate,
        )
        for i, c in enumerate(chunks)
    ]
    db.add_all(chunk_rows)
    db.flush()

    for row in chunk_rows:
        fts.index_chunk(db, row.id, row.text)

    if chunk_rows:
        embeddings = embedding_client.embed([row.text for row in chunk_rows])
        vector_store.upsert(
            collection.chroma_collection,
            ids=[f"{active_version.id}:{row.id}" for row in chunk_rows],
            embeddings=embeddings,
            metadatas=[
                {
                    "document_id": document.id,
                    "version_id": active_version.id,
                    "filename": document.filename,
                    "chunk_index": row.chunk_index,
                    "page": row.page or 0,
                    "heading": row.heading or "",
                }
                for row in chunk_rows
            ],
            documents=[row.text for row in chunk_rows],
        )

    _audit(db, "reindex", "document", document.id, f"{len(chunk_rows)} chunks")
    db.commit()

    return IngestResult(
        status="ingested",
        document_id=document.id,
        version_id=active_version.id,
        chunk_count=len(chunk_rows),
    )


def reindex_collection(
    db: Session,
    collection_id: int,
    *,
    settings: Settings,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
) -> list[IngestResult]:
    document_ids = (
        db.execute(
            select(Document.id).where(
                Document.collection_id == collection_id, Document.trashed_at.is_(None)
            )
        )
        .scalars()
        .all()
    )
    return [
        reindex_document(
            db,
            document_id,
            settings=settings,
            embedding_client=embedding_client,
            vector_store=vector_store,
        )
        for document_id in document_ids
    ]
