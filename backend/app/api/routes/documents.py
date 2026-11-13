"""Documents and versions (PLAN.md section 8). Uploads are staged and queued;
the job worker does the parsing and embedding."""

from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import DbDep, RuntimeDep
from app.api.originals import original_response
from app.api.schemas import (
    DiffOut,
    DocumentOut,
    EditTextIn,
    JobQueued,
    QueuedUpload,
    RollbackIn,
    UploadCheckIn,
    UploadCheckOut,
    UploadResponse,
    UploadRules,
    VersionOut,
    VersionTextOut,
)
from app.db.models import Chunk, Document, DocumentVersion
from app.ingest.parsers import SUPPORTED_EXTENSIONS
from app.ingest.uploads import stage_upload
from app.jobs import queue
from app.versioning import service

router = APIRouter(tags=["documents"])

_EMPTY = {"example": ""}


def split_tags(tags: str) -> list[str]:
    return [t.strip() for t in tags.split(",") if t.strip()]


def _normalize_tags(tags: str | None) -> str | None:
    return None if tags is None else ",".join(split_tags(tags))


@router.post("/documents", status_code=status.HTTP_202_ACCEPTED, response_model=UploadResponse)
def upload_documents(
    db: DbDep,
    runtime: RuntimeDep,
    files: Annotated[list[UploadFile], File(description="One or more .txt, .md, .docx, .pdf")],
    # An empty example keeps Swagger from prefilling 0 and "string".
    collection_id: Annotated[
        int | None, Form(description="Empty = default collection", json_schema_extra=_EMPTY)
    ] = None,
    tags: Annotated[
        str | None, Form(description="Comma-separated", json_schema_extra=_EMPTY)
    ] = None,
):
    """Stages each file and queues one ingest job per file. Duplicates (same
    content hash) complete as `skipped_duplicate`; a known filename with new
    content becomes a new version."""
    settings = runtime.settings
    if collection_id is None:
        collection = service.get_or_create_default_collection(db, runtime.vector_store, settings)
    else:
        collection = service.get_collection(db, collection_id)
        if not collection.is_active:
            raise service.ConflictError(f"collection {collection_id} is not active")

    queued = []
    for upload in files:
        staged = stage_upload(
            upload.file,
            upload.filename or "",
            settings.uploads_dir,
            max_bytes=settings.max_upload_mb * 1024 * 1024,
        )
        job = queue.enqueue(
            db,
            "ingest",
            {
                "staged_path": str(staged),
                "filename": staged.name,
                "collection_id": collection.id,
                "tags": _normalize_tags(tags),
            },
        )
        queued.append(QueuedUpload(job_id=job.id, filename=staged.name))
    return UploadResponse(jobs=queued)


@router.get("/documents/upload-rules", response_model=UploadRules)
def upload_rules(runtime: RuntimeDep):
    """File types and size the server accepts, so the browser can flag files early."""
    return UploadRules(
        extensions=sorted(SUPPORTED_EXTENSIONS), max_upload_mb=runtime.settings.max_upload_mb
    )


@router.post("/documents/check", response_model=list[UploadCheckOut])
def check_uploads(db: DbDep, runtime: RuntimeDep, body: UploadCheckIn):
    """Review before processing: what would happen to each file (read-only).
    The browser sends names, sizes and SHA-256 hashes, not the files."""
    if body.collection_id is None:
        collection = service.get_active_collection(db, service.DEFAULT_COLLECTION_NAME)
    else:
        collection = service.get_collection(db, body.collection_id)
        if not collection.is_active:
            raise service.ConflictError(f"collection {body.collection_id} is not active")
    checks = service.check_uploads(
        db,
        collection,
        [service.UploadCandidate(f.name, f.sha256, f.size) for f in body.files],
        max_bytes=runtime.settings.max_upload_mb * 1024 * 1024,
        supported_extensions=SUPPORTED_EXTENSIONS,
    )
    return [UploadCheckOut(**vars(c)) for c in checks]


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(
    db: DbDep,
    collection_id: int | None = None,
    trashed: Annotated[bool, Query(description="List the trash instead")] = False,
    q: Annotated[str | None, Query(description="Filename contains")] = None,
    tag: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    query = _document_rows().order_by(Document.id.desc())
    query = query.where(
        Document.trashed_at.isnot(None) if trashed else Document.trashed_at.is_(None)
    )
    if collection_id is not None:
        query = query.where(Document.collection_id == collection_id)
    if q:
        query = query.where(Document.filename.contains(q))
    if tag:
        # tags are stored comma-separated; match a whole tag
        query = query.where(("," + Document.tags + ",").contains(f",{tag.strip()},"))

    rows = db.execute(query.limit(limit).offset(offset)).all()
    return [_row_out(*row) for row in rows]


def _document_rows():
    """Documents with their version count and active version number."""
    version_count = (
        select(func.count(DocumentVersion.id))
        .where(DocumentVersion.document_id == Document.id)
        .scalar_subquery()
    )
    active_number = (
        select(DocumentVersion.version_number)
        .where(DocumentVersion.id == Document.active_version_id)
        .scalar_subquery()
    )
    return select(Document, version_count, active_number)


def _row_out(d: Document, count: int, number: int | None) -> DocumentOut:
    return DocumentOut(
        id=d.id,
        collection_id=d.collection_id,
        filename=d.filename,
        tags=split_tags(d.tags),
        active_version_id=d.active_version_id,
        active_version_number=number,
        version_count=count,
        trashed_at=d.trashed_at,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def _document_out(db, document: Document) -> DocumentOut:
    return _row_out(*db.execute(_document_rows().where(Document.id == document.id)).one())


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(db: DbDep, document_id: int):
    """Soft delete: moves the document to the 30-day trash."""
    service.soft_delete_document(db, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/documents/{document_id}/purge",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobQueued,
)
def purge_document(db: DbDep, document_id: int):
    """Delete permanently, from the trash only (409 otherwise). Cannot be undone:
    the document, its versions and its vectors are removed by a job."""
    document = service.get_document(db, document_id)
    if document.trashed_at is None:
        raise service.ConflictError(
            f"{document.filename!r} is not in the trash; move it to the trash first"
        )
    job = queue.enqueue(
        db,
        "purge_document",
        {"document_id": document.id, "filename": document.filename},
        document_id=document.id,
    )
    return JobQueued(job_id=job.id)


@router.post("/documents/{document_id}/restore", response_model=DocumentOut)
def restore_document(db: DbDep, document_id: int):
    """Takes a document out of the trash (409 if a newer one has its name)."""
    service.restore_document(db, document_id)
    return _document_out(db, service.get_document(db, document_id))


@router.post(
    "/documents/{document_id}/reindex",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobQueued,
)
def reindex_document(db: DbDep, document_id: int):
    document = service.get_document(db, document_id)
    job = queue.enqueue(
        db, "reindex_document", {"document_id": document.id}, document_id=document.id
    )
    return JobQueued(job_id=job.id)


@router.get("/documents/{document_id}/original")
def open_original(db: DbDep, runtime: RuntimeDep, document_id: int):
    """The active version's file exactly as it was uploaded (PDFs and text open in
    the browser; Word files download). Not for documents in the trash."""
    document = service.get_document(db, document_id)
    version = (
        db.get(DocumentVersion, document.active_version_id) if document.active_version_id else None
    )
    if document.trashed_at is not None or version is None:
        raise service.NotFoundError(f"document {document_id} has no original to open")
    path = service.stored_path(runtime.settings, version)
    if not path.is_file():
        raise service.NotFoundError(f"the original file of document {document_id} is missing")
    return original_response(path, document.filename)


@router.get("/documents/{document_id}/versions", response_model=list[VersionOut])
def list_versions(db: DbDep, document_id: int):
    document = service.get_document(db, document_id)
    chunk_count = (
        select(func.count(Chunk.id))
        .where(
            Chunk.version_id == DocumentVersion.id,
            Chunk.collection_id == document.collection_id,
            Chunk.retired_at.is_(None),
        )
        .scalar_subquery()
    )
    rows = db.execute(
        select(DocumentVersion, chunk_count)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version_number.desc())
    ).all()
    return [
        VersionOut(
            id=v.id,
            version_number=v.version_number,
            sha256=v.sha256,
            ext=v.ext,
            note=v.note,
            origin=v.origin,
            edited_by=v.edited_by,
            is_active=v.id == document.active_version_id,
            chunk_count=count,
            created_at=v.created_at,
        )
        for v, count in rows
    ]


@router.post(
    "/documents/{document_id}/edit",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobQueued,
)
def edit_text(db: DbDep, runtime: RuntimeDep, document_id: int, body: EditTextIn):
    """Saves edited text as a new version (queued like an upload): re-embedded,
    marked as an edit with who and what changed. Earlier versions, including the
    original file, are kept."""
    staged = service.stage_edit(db, runtime.settings, document_id, body.text)
    job = queue.enqueue(
        db,
        "ingest",
        {
            "staged_path": str(staged),
            "filename": staged.name,
            "collection_id": service.get_document(db, document_id).collection_id,
            "document_id": document_id,
            "edited_by": body.edited_by.strip(),
            "note": (body.note or "").strip() or None,
        },
        document_id=document_id,
    )
    return JobQueued(job_id=job.id)


@router.get("/documents/{document_id}/versions/{version_id}/text", response_model=VersionTextOut)
def version_text(
    db: DbDep,
    runtime: RuntimeDep,
    document_id: int,
    version_id: int,
    editable: Annotated[bool, Query(description="The editor's starting text")] = False,
):
    """The text the app extracted from one version: what it actually searches. With
    `editable`, a text or Markdown file as written (what the editor starts from)."""
    version = service.get_version(db, document_id, version_id)
    text = service.editable_text(runtime.settings, version) if editable else version.extracted_text
    return VersionTextOut(version_id=version.id, version_number=version.version_number, text=text)


@router.get("/documents/{document_id}/diff", response_model=DiffOut)
def diff_versions(
    db: DbDep,
    runtime: RuntimeDep,
    document_id: int,
    a: Annotated[int, Query(description="Version id (from)")],
    b: Annotated[int, Query(description="Version id (to)")],
):
    service.get_document(db, document_id)
    lines = service.diff_versions(db, a, b, document_id=document_id, settings=runtime.settings)
    return DiffOut(a=a, b=b, diff=lines)


@router.post("/documents/{document_id}/rollback", response_model=VersionOut)
def rollback_document(db: DbDep, document_id: int, body: RollbackIn):
    """Points the document at an earlier version. Nothing is re-embedded."""
    version = service.rollback_document(db, document_id, body.version_id)
    document = service.get_document(db, document_id)
    chunk_count = db.execute(
        select(func.count(Chunk.id)).where(
            Chunk.version_id == version.id,
            Chunk.collection_id == document.collection_id,
            Chunk.retired_at.is_(None),
        )
    ).scalar_one()
    return VersionOut(
        id=version.id,
        version_number=version.version_number,
        sha256=version.sha256,
        ext=version.ext,
        note=version.note,
        is_active=True,
        chunk_count=chunk_count,
        created_at=version.created_at,
    )
