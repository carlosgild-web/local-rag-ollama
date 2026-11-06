"""Retrieval without generation (PLAN.md section 8): the chunks and scores
an answer would be built from."""

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.api.deps import DbDep, RuntimeDep
from app.api.schemas import ChunkDetail, ChunkOut, RetrieveIn, RetrieveOut
from app.core.runtime import Runtime
from app.db.models import Collection
from app.retrieval.retrieve import RetrievedChunk, retrieve
from app.versioning import service

router = APIRouter(tags=["retrieval"])


def resolve_collection(
    db: Session, runtime: Runtime, collection_id: int | None, *, session_collection_id=None
) -> Collection:
    """For questions: never creates a collection (see collection_for_question)."""
    return service.collection_for_question(
        db, collection_id, session_collection_id=session_collection_id
    )


def chunk_out(rank: int, chunk: RetrievedChunk) -> ChunkOut:
    return ChunkOut(
        rank=rank,
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        version_id=chunk.version_id,
        filename=chunk.filename,
        page=chunk.page,
        heading=chunk.heading,
        score=chunk.score,
        text=chunk.text,
    )


@router.post("/retrieve", response_model=RetrieveOut)
def retrieve_chunks(db: DbDep, runtime: RuntimeDep, body: RetrieveIn):
    collection = resolve_collection(db, runtime, body.collection_id)
    chunks = retrieve(
        db,
        body.question,
        collection=collection,
        settings=runtime.settings,
        embedding_client=runtime.embedding_client_for(collection.embedding_model),
        vector_store=runtime.vector_store,
        top_k=body.top_k,
    )
    return RetrieveOut(
        collection_id=collection.id,
        chunks=[chunk_out(rank, c) for rank, c in enumerate(chunks, start=1)],
    )


@router.get("/chunks/{chunk_id}", response_model=ChunkDetail)
def get_chunk(db: DbDep, chunk_id: int):
    """The text behind a citation, including passages a reindex has retired."""
    chunk = service.get_chunk(db, chunk_id)
    version = chunk.version
    document = service.get_document(db, version.document_id)
    return ChunkDetail(
        id=chunk.id,
        text=chunk.text,
        document_id=document.id,
        filename=document.filename,
        collection_id=chunk.collection_id,
        version_id=version.id,
        version_number=version.version_number,
        page=chunk.page,
        heading=chunk.heading,
        retired=chunk.retired_at is not None,
    )
