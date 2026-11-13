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
import hashlib
import uuid
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


class NoTextError(ValueError):
    """The file parsed to no text at all (empty, or a scan OCR could not read)."""


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


def stored_path(settings: Settings, version: DocumentVersion) -> Path:
    """Where a version's original file is kept (content-addressed, invariant 2)."""
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


def collection_for_question(
    db: Session, collection_id: int | None, *, session_collection_id: int | None = None
) -> Collection:
    """Which shelf a question searches. Never creates one: asking on an empty
    new 'default' shelf could only ever answer "not found".

    An explicit id must be active. Otherwise the chat session's shelf is
    used (following a blue/green rebuild to its active copy), then the only
    active shelf, then an existing 'default' shelf."""
    if collection_id is not None:
        collection = get_collection(db, collection_id)
        if not collection.is_active:
            raise ConflictError(
                f"collection {collection.name!r} (#{collection.id}) is a retired copy; "
                "ask the active one"
            )
        return collection
    if session_collection_id is not None:
        previous = db.get(Collection, session_collection_id)
        if previous is not None:
            active = previous if previous.is_active else get_active_collection(db, previous.name)
            if active is not None:
                return active
    active = list(db.execute(select(Collection).where(Collection.is_active)).scalars())
    if len(active) == 1:
        return active[0]
    default = next((c for c in active if c.name == DEFAULT_COLLECTION_NAME), None)
    if default is not None:
        return default
    if not active:
        raise ConflictError("there are no collections yet: upload documents first")
    names = ", ".join(sorted(c.name for c in active))
    raise ConflictError(f"choose a collection to search ({names})")


def active_collections(db: Session) -> list[Collection]:
    """Every shelf a console question can search with "All shelves"."""
    shelves = list(
        db.execute(
            select(Collection).where(Collection.is_active.is_(True)).order_by(Collection.name)
        ).scalars()
    )
    if not shelves:
        raise ConflictError("there are no collections yet: upload documents first")
    return shelves


def portal_collections(db: Session) -> list[Collection]:
    """The shelves Luna, the employee portal assistant, searches: every
    active one the admin left visible in the portal (decision 0010)."""
    return list(
        db.execute(
            select(Collection)
            .where(Collection.is_active.is_(True), Collection.portal_visible.is_(True))
            .order_by(Collection.name)
        ).scalars()
    )


def set_portal_visible(db: Session, collection_id: int, visible: bool) -> Collection:
    """Shows or hides a shelf in the employee portal. Audited (invariant 7)."""
    collection = get_collection(db, collection_id)
    if not collection.is_active:
        raise ConflictError(f"collection {collection_id} is not active")
    if collection.portal_visible != visible:
        collection.portal_visible = visible
        record_audit(
            db,
            "collection_portal_visibility",
            "collection",
            collection.id,
            f"{collection.name}: {'visible in' if visible else 'hidden from'} the employee portal",
        )
        db.commit()
    return collection


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
            parsed = _parse(stored_path(settings, version), settings)
            prepared = _prepare(parsed, target, embedding_client)
            _clear_chunks(db, vector_store, target, version.id)
            total_chunks += _index_version(db, target, document, version, prepared, vector_store)
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
    # Taken at swap time, so a toggle made during the rebuild is kept.
    target.portal_visible = source.portal_visible
    record_audit(
        db,
        "collection_swap",
        "collection",
        target.id,
        f"blue/green swap from collection {source.id} ({source.chroma_collection})",
    )
    db.commit()


# --- Indexing helpers -------------------------------------------------------


@dataclass
class _Prepared:
    """Chunks and their embeddings, computed without touching the database."""

    chunks: list
    embeddings: list[list[float]]


def _prepare(
    parsed: ParsedDocument, collection: Collection, embedding_client: EmbeddingClient
) -> _Prepared:
    """The slow part of indexing (chunking and the embedding call), done
    before any write. SQLite allows one writer, so a write transaction held
    open through the embedding call blocked every other request: a Cancel
    click waited 9-12 s in the 2026-11-06 end-to-end test."""
    chunks = chunk_blocks(
        parsed.blocks,
        chunk_size_tokens=collection.chunk_size_tokens,
        overlap_pct=collection.chunk_overlap_pct,
    )
    embeddings = embedding_client.embed([c.text for c in chunks]) if chunks else []
    return _Prepared(chunks=chunks, embeddings=embeddings)


def _index_version(
    db: Session,
    collection: Collection,
    document: Document,
    version: DocumentVersion,
    prepared: _Prepared,
    vector_store: VectorStore,
) -> int:
    """Writes one prepared version into one collection: SQLite rows, FTS5, vectors."""
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
        for i, c in enumerate(prepared.chunks)
    ]
    embeddings = prepared.embeddings
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


# --- Upload review (read-only) -----------------------------------------------


@dataclass
class UploadCandidate:
    name: str
    sha256: str
    size: int


@dataclass
class UploadCheck:
    """What would happen to one file if it were uploaded now."""

    name: str
    status: str  # new | new_version | duplicate | name_in_trash | unsupported | empty | too_large
    message: str
    document_id: int | None = None
    existing_filename: str | None = None
    existing_shelf: str | None = None
    existing_version: int | None = None
    next_version: int | None = None
    existing_since: dt.datetime | None = None


def check_uploads(
    db: Session,
    collection: Collection | None,
    candidates: list[UploadCandidate],
    *,
    max_bytes: int,
    supported_extensions: set[str],
) -> list[UploadCheck]:
    """Predicts, without writing anything, how ingest_document would treat
    each file: the same rules (global content hash first, then the same
    filename on the shelf), so the user can review before processing.
    `collection` None means the default shelf, which may not exist yet."""
    shelves = {c.id: c.name for c in db.execute(select(Collection)).scalars()}
    results = []
    for item in candidates:
        suffix = Path(item.name).suffix.lower()
        if suffix not in supported_extensions:
            kinds = ", ".join(sorted(supported_extensions))
            results.append(
                UploadCheck(
                    item.name, "unsupported", f"This file type can't be read (supported: {kinds})."
                )
            )
            continue
        if item.size == 0:
            results.append(UploadCheck(item.name, "empty", "The file is empty."))
            continue
        if item.size > max_bytes:
            limit = max_bytes // (1024 * 1024)
            results.append(
                UploadCheck(
                    item.name, "too_large", f"The file is larger than the {limit} MB limit."
                )
            )
            continue

        version = db.execute(
            select(DocumentVersion).where(DocumentVersion.sha256 == item.sha256)
        ).scalar_one_or_none()
        if version is not None:
            document = db.get(Document, version.document_id)
            shelf = shelves.get(document.collection_id, f"#{document.collection_id}")
            label = "" if document.filename == item.name else f" as '{document.filename}'"
            then = (
                " It's in the trash: restore it there instead (Library → Trash → Restore)."
                if document.trashed_at
                else " It will be skipped."
            )
            results.append(
                UploadCheck(
                    item.name,
                    "duplicate",
                    f"Already in the library{label}: version {version.version_number} on shelf "
                    f"'{shelf}'.{then}",
                    document_id=document.id,
                    existing_filename=document.filename,
                    existing_shelf=shelf,
                    existing_version=version.version_number,
                    existing_since=version.created_at,
                )
            )
            continue

        if collection is None:
            results.append(UploadCheck(item.name, "new", "New document."))
            continue
        same_name = (
            db.execute(
                select(Document)
                .where(Document.collection_id == collection.id, Document.filename == item.name)
                .order_by(Document.trashed_at.is_(None).desc(), Document.id.desc())
            )
            .scalars()
            .first()
        )
        if same_name is not None and same_name.trashed_at is None:
            active = (
                db.get(DocumentVersion, same_name.active_version_id)
                if same_name.active_version_id
                else None
            )
            current = active.version_number if active else None
            next_version = _next_version_number(db, same_name.id)
            results.append(
                UploadCheck(
                    item.name,
                    "new_version",
                    f"A different version is already on this shelf (v{current}). This becomes "
                    f"v{next_version} and the active version; the old one is kept.",
                    document_id=same_name.id,
                    existing_filename=same_name.filename,
                    existing_shelf=collection.name,
                    existing_version=current,
                    next_version=next_version,
                    existing_since=active.created_at if active else None,
                )
            )
        elif same_name is not None:
            results.append(
                UploadCheck(
                    item.name,
                    "name_in_trash",
                    "A document with this name is in the trash. Uploading creates a new, separate "
                    "document; to keep its history, restore the old one first and upload again.",
                    document_id=same_name.id,
                    existing_filename=same_name.filename,
                    existing_shelf=collection.name,
                    existing_since=same_name.trashed_at,
                )
            )
        else:
            results.append(UploadCheck(item.name, "new", "New document."))
    return results


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
    progress: ProgressCallback | None = None,
    into_document_id: int | None = None,
    edited_by: str | None = None,
    note: str | None = None,
) -> IngestResult:
    """`filename` overrides `source_path.name` (uploads are staged under a
    temporary name). `progress` is called once the slow work is done and
    before anything is written, so a cancelled job stops cleanly there.
    `into_document_id` adds the file as a new version of that document even if
    its name differs (a near-duplicate the user chose to merge); the version's
    note records the name it was uploaded under. `edited_by` marks the version as
    an edit made in the app (with `note` saying what changed)."""
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

    # Parse before storing anything: a file with no text would become a
    # document that can never answer (end-to-end test 2026-11-06).
    parsed = _parse(source_path, settings)
    if not parsed.full_text.strip():
        raise NoTextError(f"no text could be read from {filename!r}; it is empty or a blank scan")
    prepared = _prepare(parsed, collection, embedding_client)
    if progress:
        progress(0.8)  # raises JobCancelled if a cancel came in; nothing written yet

    _, stored_path = file_store.store_file(source_path, settings.files_dir)

    if into_document_id is not None:
        document = db.get(Document, into_document_id)
        if document is None or document.trashed_at is not None:
            raise NotFoundError(f"document {into_document_id} is gone; add the file again")
        if filename != document.filename and edited_by is None:
            note = f"Uploaded as '{filename}'"
    else:
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

    version = DocumentVersion(
        document_id=document.id,
        version_number=_next_version_number(db, document.id),
        sha256=sha256,
        original_path=str(stored_path),
        ext=source_path.suffix.lower(),
        extracted_text=parsed.full_text,
        note=note,
        origin="edit" if edited_by else "upload",
        edited_by=edited_by,
    )
    db.add(version)
    db.flush()

    chunk_count = _index_version(db, collection, document, version, prepared, vector_store)

    document.active_version_id = version.id
    document.updated_at = utcnow()
    if edited_by:
        detail = f"version {version.version_number} edited by {edited_by}"
        record_audit(db, "edit", "document", document.id, detail + (f": {note}" if note else ""))
    else:
        detail = f"version {version.version_number}" + (f" ({note.lower()})" if note else "")
        record_audit(db, "upload", "document", document.id, detail)
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


def get_chunk(db: Session, chunk_id: int) -> Chunk:
    chunk = db.get(Chunk, chunk_id)
    if chunk is None:
        raise NotFoundError(f"chunk {chunk_id} not found")
    return chunk


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
    document.updated_at = utcnow()
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
    """Takes a document out of the trash. Refused if a document with the same
    name was added to that shelf since: two would answer as one."""
    document = get_document(db, document_id)
    if document.trashed_at is None:
        return
    clash = db.execute(
        select(Document).where(
            Document.collection_id == document.collection_id,
            Document.filename == document.filename,
            Document.trashed_at.is_(None),
            Document.id != document.id,
        )
    ).scalar_one_or_none()
    if clash is not None:
        raise ConflictError(
            f"'{document.filename}' was uploaded again after it was deleted; "
            "delete or rename the newer one before restoring this one"
        )
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


TEXT_FILE_EXTENSIONS = {".txt", ".md"}


def editable_text(settings: Settings, version: DocumentVersion) -> str:
    """What the editor starts from: a text or Markdown file as it was written (so
    tables and line breaks survive), or the text extracted from a PDF or Word file."""
    if version.ext in TEXT_FILE_EXTENSIONS:
        path = stored_path(settings, version)
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return version.extracted_text


def stage_edit(db: Session, settings: Settings, document_id: int, text: str) -> Path:
    """Checks an edit and writes it to a staging folder, ready to be ingested as the
    document's next version: in the same format for text and Markdown files, as a
    .txt file (which keeps the lines as typed) for text taken from a PDF or Word file."""
    document = get_document(db, document_id)
    if document.trashed_at is not None:
        raise NotFoundError(f"document {document_id} is in the trash")
    active = (
        db.get(DocumentVersion, document.active_version_id) if document.active_version_id else None
    )
    if active is not None and text.strip() == editable_text(settings, active).strip():
        raise ConflictError("nothing changed: the text is the same as the active version")
    ext = active.ext if active is not None and active.ext in TEXT_FILE_EXTENSIONS else ".txt"
    data = text.encode("utf-8")
    sha256 = hashlib.sha256(data).hexdigest()
    same = db.execute(
        select(DocumentVersion).where(DocumentVersion.sha256 == sha256)
    ).scalar_one_or_none()
    if same is not None:
        raise ConflictError(
            f"this exact text is already version {same.version_number}: restore it instead"
        )
    staging = settings.uploads_dir / uuid.uuid4().hex
    staging.mkdir(parents=True)
    path = staging / (Path(document.filename).stem + ext)
    path.write_bytes(data)
    return path


def get_version(db: Session, document_id: int, version_id: int) -> DocumentVersion:
    version = db.get(DocumentVersion, version_id)
    if version is None or version.document_id != document_id:
        raise NotFoundError(f"version {version_id} does not belong to document {document_id}")
    return version


def diff_versions(
    db: Session,
    version_a_id: int,
    version_b_id: int,
    *,
    document_id: int | None = None,
    settings: Settings | None = None,
) -> list[str]:
    """Line diff of two versions. With `settings`, text and Markdown files are compared
    as written (tables and line breaks intact) rather than as extracted."""
    version_a = db.get(DocumentVersion, version_a_id)
    version_b = db.get(DocumentVersion, version_b_id)
    if version_a is None or version_b is None:
        raise NotFoundError("one or both versions not found")
    if document_id is not None and {version_a.document_id, version_b.document_id} != {document_id}:
        raise NotFoundError(f"both versions must belong to document {document_id}")

    def text(version: DocumentVersion) -> str:
        return editable_text(settings, version) if settings else version.extracted_text

    return text_diff(
        text(version_a),
        text(version_b),
        f"v{version_a.version_number}",
        f"v{version_b.version_number}",
    )


def text_diff(text_a: str, text_b: str, name_a: str, name_b: str) -> list[str]:
    """Unified line diff of two extracted texts (what the app searches)."""
    return list(
        difflib.unified_diff(
            text_a.splitlines(), text_b.splitlines(), fromfile=name_a, tofile=name_b, lineterm=""
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

    parsed = _parse(stored_path(settings, active_version), settings)
    prepared = _prepare(parsed, collection, embedding_client)
    _clear_chunks(db, vector_store, collection, active_version.id)
    chunk_count = _index_version(db, collection, document, active_version, prepared, vector_store)

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
