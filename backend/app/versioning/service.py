"""The versioning service layer (CLAUDE.md invariant 1).

All writes to SQLite, Chroma, and the file store go through this module
(plus app/ingest's pure parsing/chunking/file-store helpers, which this
module calls into). Routes and the CLI never write directly.

Implements CLAUDE.md invariants 2-4 and 7, and PLAN.md section 5:
content-addressed files, duplicate-by-hash skip, new-version-on-change,
rollback-by-pointer-flip (no re-embedding), soft delete with trash, and
blue/green collection rebuilds on embedding/chunking changes.
"""

import datetime as dt
import difflib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import fts
from app.db.models import (
    AuditLog,
    Chunk,
    Collection,
    Document,
    DocumentVersion,
    MessageSource,
    utcnow,
)
from app.ingest import file_store
from app.ingest.chunker import chunk_blocks
from app.ingest.parsers import SUPPORTED_EXTENSIONS, parse_file
from app.ingest.parsers.base import ParsedDocument
from app.llm.base import EmbeddingClient
from app.retrieval.vector_store import VectorStore

DEFAULT_COLLECTION_NAME = "default"
DEFAULT_TRASH_DAYS = 30

# Called with a 0..1 fraction as long-running operations advance. The job
# worker passes one that also raises JobCancelled when cancel is requested.
ProgressCallback = Callable[[float], None]


class NotFoundError(ValueError):
    pass


class ConflictError(ValueError):
    pass


@dataclass
class IngestResult:
    status: str  # "ingested" | "skipped_duplicate"
    document_id: int
    version_id: int | None = None
    chunk_count: int = 0


def record_audit(
    db: Session, action: str, entity_type: str, entity_id: int | None, detail: str = ""
) -> None:
    """Adds an audit row to the current transaction (invariant 7). Callers commit."""
    db.add(AuditLog(action=action, entity_type=entity_type, entity_id=entity_id, detail=detail))


def audit_event(
    db: Session, action: str, entity_type: str, entity_id: int | None, detail: str = ""
) -> None:
    """Records and commits a standalone audit event (e.g. a model pull)."""
    record_audit(db, action, entity_type, entity_id, detail)
    db.commit()


def discover_files(path: Path) -> list[Path]:
    """A single file, or every supported file under a directory, sorted."""
    if path.is_file():
        return [path]
    return sorted(
        p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def _vector_metadata(collection: Collection) -> dict:
    return {
        "embedding_model": collection.embedding_model,
        "chunk_size_tokens": collection.chunk_size_tokens,
        "chunk_overlap_pct": collection.chunk_overlap_pct,
    }


def _vector_id(chunk: Chunk) -> str:
    return f"{chunk.version_id}:{chunk.id}"


def _parse(path: Path, settings: Settings) -> ParsedDocument:
    return parse_file(
        path,
        ocr_lang=settings.ocr_lang,
        ocr_min_text_chars=settings.ocr_min_text_chars,
        tesseract_cmd=settings.tesseract_cmd,
        tessdata_prefix=settings.tessdata_prefix,
    )


def _stored_path(settings: Settings, version: DocumentVersion) -> Path:
    return file_store.files_path_for(settings.files_dir, version.sha256, version.ext)


# --- Collections (invariant 4: embedding model per collection, blue/green) --


def get_active_collection(db: Session, name: str) -> Collection | None:
    return db.execute(
        select(Collection).where(Collection.name == name, Collection.is_active.is_(True))
    ).scalar_one_or_none()


def get_collection(db: Session, collection_id: int) -> Collection:
    collection = db.get(Collection, collection_id)
    if collection is None:
        raise NotFoundError(f"collection {collection_id} not found")
    return collection


def create_collection(
    db: Session,
    vector_store: VectorStore,
    *,
    name: str,
    embedding_model: str,
    chunk_size_tokens: int = 600,
    chunk_overlap_pct: float = 0.12,
) -> Collection:
    """Creates a new, active collection. Changing the model or chunking of an
    existing one goes through `start_collection_rebuild` instead."""
    if get_active_collection(db, name) is not None:
        raise ConflictError(f"collection '{name}' already exists")

    collection = _new_generation(
        db,
        vector_store,
        name=name,
        embedding_model=embedding_model,
        chunk_size_tokens=chunk_size_tokens,
        chunk_overlap_pct=chunk_overlap_pct,
        is_active=True,
    )
    record_audit(db, "collection_create", "collection", collection.id, collection.chroma_collection)
    db.commit()
    return collection


def _new_generation(
    db: Session,
    vector_store: VectorStore,
    *,
    name: str,
    embedding_model: str,
    chunk_size_tokens: int,
    chunk_overlap_pct: float,
    is_active: bool,
) -> Collection:
    generation = _next_generation(db, name)
    collection = Collection(
        name=name,
        chroma_collection=f"{name}__g{generation}",
        embedding_model=embedding_model,
        chunk_size_tokens=chunk_size_tokens,
        chunk_overlap_pct=chunk_overlap_pct,
        is_active=is_active,
    )
    db.add(collection)
    db.flush()
    vector_store.get_or_create_collection(
        collection.chroma_collection, metadata=_vector_metadata(collection)
    )
    return collection


def _next_generation(db: Session, name: str) -> int:
    rows = db.execute(select(Collection.id).where(Collection.name == name)).scalars().all()
    return len(rows) + 1


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


def start_collection_rebuild(
    db: Session,
    vector_store: VectorStore,
    source_collection_id: int,
    *,
    embedding_model: str,
    chunk_size_tokens: int,
    chunk_overlap_pct: float,
) -> Collection:
    """Blue/green step 1: creates the next, still-inactive generation of a
    collection. The source keeps serving queries until `swap_collection`."""
    source = get_collection(db, source_collection_id)
    if not source.is_active:
        raise ConflictError(f"collection {source.id} is not active")

    target = _new_generation(
        db,
        vector_store,
        name=source.name,
        embedding_model=embedding_model,
        chunk_size_tokens=chunk_size_tokens,
        chunk_overlap_pct=chunk_overlap_pct,
        is_active=False,
    )
    record_audit(
        db,
        "collection_rebuild_start",
        "collection",
        target.id,
        f"from collection {source.id} ({source.chroma_collection}); model {embedding_model}, "
        f"chunk size {chunk_size_tokens}, overlap {chunk_overlap_pct}",
    )
    db.commit()
    return target


def build_collection(
    db: Session,
    source_collection_id: int,
    target_collection_id: int,
    *,
    settings: Settings,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    progress: ProgressCallback | None = None,
) -> int:
    """Blue/green step 2: re-chunks and re-embeds every version of every
    document (trashed ones too, so restore and rollback keep working) into
    the target collection. Returns the number of chunks written."""
    source = get_collection(db, source_collection_id)
    target = get_collection(db, target_collection_id)
    documents = (
        db.execute(select(Document).where(Document.collection_id == source.id)).scalars().all()
    )

    total_chunks = 0
    for i, document in enumerate(documents):
        if progress:
            progress(i / max(len(documents), 1))
        for version in document.versions:
            _clear_chunks(db, vector_store, target, version.id)
            parsed = _parse(_stored_path(settings, version), settings)
            total_chunks += _index_version(
                db, target, document, version, parsed, embedding_client, vector_store
            )
        db.commit()

    if progress:
        progress(1.0)
    return total_chunks


def swap_collection(db: Session, source_collection_id: int, target_collection_id: int) -> None:
    """Blue/green step 3: activates the target, repoints its documents, and
    keeps the source (and its vectors) inactive until someone purges it."""
    source = get_collection(db, source_collection_id)
    target = get_collection(db, target_collection_id)
    if source.name != target.name:
        raise ConflictError("can only swap generations of the same collection")

    documents = (
        db.execute(select(Document).where(Document.collection_id == source.id)).scalars().all()
    )
    for document in documents:
        document.collection_id = target.id
    source.is_active = False
    target.is_active = True
    record_audit(
        db,
        "collection_swap",
        "collection",
        target.id,
        f"blue/green swap from collection {source.id} ({source.chroma_collection})",
    )
    db.commit()


# --- Indexing helpers -------------------------------------------------------


def _index_version(
    db: Session,
    collection: Collection,
    document: Document,
    version: DocumentVersion,
    parsed: ParsedDocument,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
) -> int:
    """Chunks one version into one collection: SQLite rows, FTS5, vectors."""
    chunks = chunk_blocks(
        parsed.blocks,
        chunk_size_tokens=collection.chunk_size_tokens,
        overlap_pct=collection.chunk_overlap_pct,
    )
    rows = [
        Chunk(
            version_id=version.id,
            collection_id=collection.id,
            chunk_index=i,
            text=c.text,
            page=c.page,
            heading=c.heading,
            token_estimate=c.token_estimate,
        )
        for i, c in enumerate(chunks)
    ]
    # Embed before the first write: the flush takes SQLite's write lock, and
    # holding it through a slow embedding call blocks every other request
    # (a Cancel click waited 9 s in the 2026-11-06 end-to-end test).
    embeddings = embedding_client.embed([row.text for row in rows]) if rows else []
    db.add_all(rows)
    db.flush()

    for row in rows:
        fts.index_chunk(db, row.id, row.text)

    if rows:
        vector_store.upsert(
            collection.chroma_collection,
            ids=[_vector_id(row) for row in rows],
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
                for row in rows
            ],
            documents=[row.text for row in rows],
        )
    return len(rows)


def _cited_chunk_ids(db: Session, chunk_ids: list[int]) -> set[int]:
    if not chunk_ids:
        return set()
    return set(
        db.execute(
            select(MessageSource.chunk_id).where(MessageSource.chunk_id.in_(chunk_ids)).distinct()
        ).scalars()
    )


def _clear_chunks(
    db: Session, vector_store: VectorStore, collection: Collection, version_id: int
) -> None:
    """Takes a version's live chunks in `collection` out of search. Chunks a
    saved answer cites are retired (kept, never served); the rest are deleted."""
    chunks = (
        db.execute(
            select(Chunk).where(
                Chunk.version_id == version_id,
                Chunk.collection_id == collection.id,
                Chunk.retired_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    if not chunks:
        return
    vector_store.delete(collection.chroma_collection, [_vector_id(c) for c in chunks])
    cited = _cited_chunk_ids(db, [c.id for c in chunks])
    now = utcnow()
    for chunk in chunks:
        fts.remove_chunk(db, chunk.id, chunk.text)
        if chunk.id in cited:
            chunk.retired_at = now
        else:
            db.delete(chunk)
    db.flush()


# --- Ingestion (invariants 2, 3) -------------------------------------------


def ingest_document(
    db: Session,
    *,
    collection: Collection,
    source_path: Path,
    settings: Settings,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    filename: str | None = None,
    tags: str | None = None,
) -> IngestResult:
    """`filename` overrides `source_path.name` (uploads are staged under a
    temporary name)."""
    filename = filename or source_path.name
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

    _, stored_path = file_store.store_file(source_path, settings.files_dir)

    document = db.execute(
        select(Document).where(
            Document.collection_id == collection.id,
            Document.filename == filename,
            Document.trashed_at.is_(None),
        )
    ).scalar_one_or_none()
    if document is None:
        document = Document(collection_id=collection.id, filename=filename)
        db.add(document)
        db.flush()
    if tags is not None:
        document.tags = tags

    parsed = _parse(source_path, settings)
    version = DocumentVersion(
        document_id=document.id,
        version_number=_next_version_number(db, document.id),
        sha256=sha256,
        original_path=str(stored_path),
        ext=source_path.suffix.lower(),
        extracted_text=parsed.full_text,
    )
    db.add(version)
    db.flush()

    chunk_count = _index_version(
        db, collection, document, version, parsed, embedding_client, vector_store
    )

    document.active_version_id = version.id
    record_audit(db, "upload", "document", document.id, f"version {version.version_number}")
    db.commit()

    return IngestResult(
        status="ingested", document_id=document.id, version_id=version.id, chunk_count=chunk_count
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


def get_document(db: Session, document_id: int) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError(f"document {document_id} not found")
    return document


def rollback_document(db: Session, document_id: int, version_id: int) -> DocumentVersion:
    document = get_document(db, document_id)
    version = db.get(DocumentVersion, version_id)
    if version is None or version.document_id != document_id:
        raise NotFoundError(f"version {version_id} does not belong to document {document_id}")

    document.active_version_id = version.id
    record_audit(db, "rollback", "document", document.id, f"to version {version.version_number}")
    db.commit()
    return version


# --- Soft delete / trash (invariant 3) -------------------------------------


def soft_delete_document(db: Session, document_id: int) -> None:
    document = get_document(db, document_id)
    if document.trashed_at is not None:
        return
    document.trashed_at = utcnow()
    record_audit(db, "delete", "document", document.id, "soft delete")
    db.commit()


def restore_document(db: Session, document_id: int) -> None:
    document = get_document(db, document_id)
    document.trashed_at = None
    record_audit(db, "restore", "document", document.id, "")
    db.commit()


def purge_expired_trash(
    db: Session, vector_store: VectorStore, *, older_than_days: int = DEFAULT_TRASH_DAYS
) -> list[int]:
    """Hard-deletes documents trashed more than `older_than_days` ago, with
    their chunks in every collection generation. Returns the purged ids."""
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
        versions = list(document.versions)
        unlinked = 0
        for version in versions:
            chunks = db.execute(select(Chunk).where(Chunk.version_id == version.id)).scalars().all()
            # Retired chunks are already out of Chroma and FTS; deleting an
            # FTS row that isn't there would corrupt the index.
            live = [c for c in chunks if c.retired_at is None]
            by_collection: dict[int, list[Chunk]] = {}
            for chunk in live:
                by_collection.setdefault(chunk.collection_id, []).append(chunk)
            for collection_id, collection_chunks in by_collection.items():
                collection = db.get(Collection, collection_id)
                vector_store.delete(
                    collection.chroma_collection, [_vector_id(c) for c in collection_chunks]
                )
            for chunk in live:
                fts.remove_chunk(db, chunk.id, chunk.text)
            # Purge is the deliberate permanent delete: answers keep their
            # text but lose the links to the purged chunks.
            unlinked += db.execute(
                delete(MessageSource).where(MessageSource.chunk_id.in_([c.id for c in chunks]))
            ).rowcount
            for chunk in chunks:
                db.delete(chunk)
            db.delete(version)
        purged_ids.append(document.id)
        db.delete(document)
        detail = f"{len(versions)} version(s)"
        if unlinked:
            detail += f", {unlinked} answer source link(s) removed"
        record_audit(db, "purge", "document", document.id, detail)

    db.commit()
    return purged_ids


# --- Diff (PLAN.md section 5) ----------------------------------------------


def diff_versions(
    db: Session, version_a_id: int, version_b_id: int, *, document_id: int | None = None
) -> list[str]:
    version_a = db.get(DocumentVersion, version_a_id)
    version_b = db.get(DocumentVersion, version_b_id)
    if version_a is None or version_b is None:
        raise NotFoundError("one or both versions not found")
    if document_id is not None and {version_a.document_id, version_b.document_id} != {document_id}:
        raise NotFoundError(f"both versions must belong to document {document_id}")

    return list(
        difflib.unified_diff(
            version_a.extracted_text.splitlines(),
            version_b.extracted_text.splitlines(),
            fromfile=f"v{version_a.version_number}",
            tofile=f"v{version_b.version_number}",
            lineterm="",
        )
    )


# --- In-place reindex (same model and chunking, e.g. after a parser fix) --


def reindex_document(
    db: Session,
    document_id: int,
    *,
    settings: Settings,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
) -> IngestResult:
    document = get_document(db, document_id)
    if document.active_version_id is None:
        raise ConflictError(f"document {document_id} has no active version to reindex")
    collection = get_collection(db, document.collection_id)
    active_version = db.get(DocumentVersion, document.active_version_id)

    _clear_chunks(db, vector_store, collection, active_version.id)
    parsed = _parse(_stored_path(settings, active_version), settings)
    chunk_count = _index_version(
        db, collection, document, active_version, parsed, embedding_client, vector_store
    )

    record_audit(db, "reindex", "document", document.id, f"{chunk_count} chunks")
    db.commit()

    return IngestResult(
        status="ingested",
        document_id=document.id,
        version_id=active_version.id,
        chunk_count=chunk_count,
    )


def reindex_collection(
    db: Session,
    collection_id: int,
    *,
    settings: Settings,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    progress: ProgressCallback | None = None,
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
    results = []
    for i, document_id in enumerate(document_ids):
        if progress:
            progress(i / max(len(document_ids), 1))
        results.append(
            reindex_document(
                db,
                document_id,
                settings=settings,
                embedding_client=embedding_client,
                vector_store=vector_store,
            )
        )
    if progress:
        progress(1.0)
    return results
