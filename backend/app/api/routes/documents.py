"""Documents and versions (PLAN.md section 8). Uploads are staged and queued;
the job worker does the parsing and embedding."""

from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import DbDep, RuntimeDep
from app.api.schemas import (
    DiffOut,
    DocumentOut,
    JobQueued,
    QueuedUpload,
    RollbackIn,
    UploadResponse,
    VersionOut,
)
from app.db.models import Chunk, Document, DocumentVersion
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
    query = select(Document, version_count, active_number).order_by(Document.id.desc())
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
    return [
        DocumentOut(
            id=d.id,
            collection_id=d.collection_id,
            filename=d.filename,
            tags=split_tags(d.tags),
            active_version_id=d.active_version_id,
            active_version_number=number,
            version_count=count,
            trashed_at=d.trashed_at,
            created_at=d.created_at,
        )
        for d, count, number in rows
    ]


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(db: DbDep, document_id: int):
    """Soft delete: moves the document to the 30-day trash."""
    service.soft_delete_document(db, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@router.get("/documents/{document_id}/versions", response_model=list[VersionOut])
def list_versions(db: DbDep, document_id: int):
    document = service.get_document(db, document_id)
    chunk_count = (
        select(func.count(Chunk.id))
        .where(
            Chunk.version_id == DocumentVersion.id,
            Chunk.collection_id == document.collection_id,
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
            is_active=v.id == document.active_version_id,
            chunk_count=count,
            created_at=v.created_at,
        )
        for v, count in rows
    ]


@router.get("/documents/{document_id}/diff", response_model=DiffOut)
def diff_versions(
    db: DbDep,
    document_id: int,
    a: Annotated[int, Query(description="Version id (from)")],
    b: Annotated[int, Query(description="Version id (to)")],
):
    service.get_document(db, document_id)
    return DiffOut(a=a, b=b, diff=service.diff_versions(db, a, b, document_id=document_id))


@router.post("/documents/{document_id}/rollback", response_model=VersionOut)
def rollback_document(db: DbDep, document_id: int, body: RollbackIn):
    """Points the document at an earlier version. Nothing is re-embedded."""
    version = service.rollback_document(db, document_id, body.version_id)
    document = service.get_document(db, document_id)
    chunk_count = db.execute(
        select(func.count(Chunk.id)).where(
            Chunk.version_id == version.id, Chunk.collection_id == document.collection_id
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
