"""Collections (PLAN.md section 8). Changing the embedding model or chunking
of a collection is a background blue/green rebuild (invariant 4)."""

from typing import Annotated

from fastapi import APIRouter, Body, status
from sqlalchemy import func, select

from app.api.deps import DbDep, RuntimeDep
from app.api.schemas import (
    CollectionIn,
    CollectionOut,
    CollectionPatch,
    CollectionReindexIn,
    JobQueued,
)
from app.db.models import Collection, Document
from app.jobs import queue
from app.versioning import service

router = APIRouter(tags=["collections"])


def _out(collection: Collection, document_count: int) -> CollectionOut:
    out = CollectionOut.model_validate(collection)
    out.document_count = document_count
    return out


@router.get("/collections", response_model=list[CollectionOut])
def list_collections(db: DbDep, include_inactive: bool = False):
    """Active collections; `include_inactive` adds older and in-progress
    blue/green generations."""
    document_count = (
        select(func.count(Document.id))
        .where(Document.collection_id == Collection.id, Document.trashed_at.is_(None))
        .scalar_subquery()
    )
    query = select(Collection, document_count).order_by(Collection.name, Collection.id)
    if not include_inactive:
        query = query.where(Collection.is_active.is_(True))
    return [_out(c, count) for c, count in db.execute(query).all()]


@router.post("/collections", status_code=status.HTTP_201_CREATED, response_model=CollectionOut)
def create_collection(db: DbDep, runtime: RuntimeDep, body: CollectionIn):
    settings = runtime.settings
    collection = service.create_collection(
        db,
        runtime.vector_store,
        name=body.name,
        embedding_model=body.embedding_model or settings.embedding_model,
        chunk_size_tokens=body.chunk_size_tokens or settings.chunk_size_tokens,
        chunk_overlap_pct=(
            body.chunk_overlap_pct
            if body.chunk_overlap_pct is not None
            else settings.chunk_overlap_pct
        ),
    )
    return _out(collection, 0)


@router.patch("/collections/{collection_id}", response_model=CollectionOut)
def update_collection(db: DbDep, collection_id: int, body: CollectionPatch):
    """Shows or hides the shelf in the employee portal (decision 0010)."""
    collection = service.set_portal_visible(db, collection_id, body.portal_visible)
    document_count = db.execute(
        select(func.count(Document.id)).where(
            Document.collection_id == collection.id, Document.trashed_at.is_(None)
        )
    ).scalar_one()
    return _out(collection, document_count)


@router.post(
    "/collections/{collection_id}/reindex",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobQueued,
)
def reindex_collection(
    db: DbDep,
    runtime: RuntimeDep,
    collection_id: int,
    body: Annotated[CollectionReindexIn | None, Body()] = None,
):
    """No body, or the same settings: re-chunk and re-embed in place.
    A new embedding model or chunking: build a new generation in the
    background and swap it in when done; the current one keeps serving."""
    body = body or CollectionReindexIn()
    collection = service.get_collection(db, collection_id)
    if not collection.is_active:
        raise service.ConflictError(f"collection {collection_id} is not active")

    target_config = {
        "embedding_model": body.embedding_model or collection.embedding_model,
        "chunk_size_tokens": body.chunk_size_tokens or collection.chunk_size_tokens,
        "chunk_overlap_pct": (
            body.chunk_overlap_pct
            if body.chunk_overlap_pct is not None
            else collection.chunk_overlap_pct
        ),
    }
    current_config = {key: getattr(collection, key) for key in target_config}

    if target_config == current_config:
        job = queue.enqueue(db, "reindex_collection", {"collection_id": collection.id})
        return JobQueued(job_id=job.id, mode="in_place")

    target = service.start_collection_rebuild(
        db, runtime.vector_store, collection.id, **target_config
    )
    job = queue.enqueue(
        db,
        "rebuild_collection",
        {"source_collection_id": collection.id, "target_collection_id": target.id},
    )
    return JobQueued(job_id=job.id, mode="blue_green", target_collection_id=target.id)
