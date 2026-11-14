"""Retrieval without generation (PLAN.md section 8): the chunks and scores
an answer would be built from."""

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.api.deps import DbDep, RuntimeDep
from app.api.schemas import (
    ChunkDetail,
    ChunkOut,
    InspectChunkOut,
    InspectIn,
    InspectOut,
    InspectParameters,
    InspectTimings,
    RetrieveIn,
    RetrieveOut,
)
from app.core.runtime import Runtime
from app.db.models import Collection
from app.retrieval.glossary import expand_with_glossary
from app.retrieval.inspector import inspect_retrieval
from app.retrieval.onnx_reranker import model_ready
from app.retrieval.retrieve import RetrievedChunk, retrieve
from app.versioning import profiles, service

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
        expand_with_glossary(db, body.question),
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


def reranker_available(runtime: Runtime) -> bool:
    return runtime.reranker is not None and model_ready(runtime.settings.reranker_dir)


@router.post("/retrieve/inspect", response_model=InspectOut)
def inspect(db: DbDep, runtime: RuntimeDep, body: InspectIn):
    """The retrieval inspector: every fused candidate with its vector and
    keyword ranks and scores, which ones the model would see, and the final
    prompt. Read-only; the defaults match the console chat."""
    settings = runtime.settings
    profile = profiles.get_active_profile(
        db, settings, body.profile or profiles.DEFAULT_PROFILE_NAME
    )
    if body.scope == "all":
        collections = service.active_collections(db)
    elif body.scope == "portal":
        collections = service.portal_collections(db)
    else:
        collections = [resolve_collection(db, runtime, body.collection_id)]

    available = reranker_available(runtime)
    rerank = settings.rerank_enabled if body.rerank is None else body.rerank
    if body.rerank and not available:
        raise service.ConflictError(
            "the reranker model isn't downloaded; run `python -m app.cli reranker-download`"
        )

    result = inspect_retrieval(
        db,
        body.question,
        collections=collections,
        profile=profile,
        settings=settings,
        embedding_client_for=runtime.embedding_client_for,
        vector_store=runtime.vector_store,
        cache=runtime.question_cache,
        mode=body.mode,
        top_k=body.top_k,
        candidates=body.candidates,
        vector_weight=body.vector_weight,
        min_cosine=body.min_cosine,
        reranker=runtime.reranker if rerank and available else None,
        include_prompt=body.include_prompt,
    )
    return InspectOut(
        question=result.question,
        expanded_question=result.expanded_question,
        collection_ids=result.collection_ids,
        profile_id=profile.id,
        profile_name=profile.name,
        profile_version=profile.version,
        parameters=InspectParameters(**result.parameters),
        reranker_available=available,
        chunks=[
            InspectChunkOut(
                **chunk_out(i.rank, i.chunk).model_dump(),
                sent=i.sent,
                vector_rank=i.chunk.vector_rank,
                vector_score=i.chunk.vector_score,
                keyword_rank=i.chunk.keyword_rank,
                keyword_score=i.chunk.keyword_score,
                fused_score=i.chunk.fused_score,
                rerank_score=i.rerank_score,
            )
            for i in result.chunks
        ],
        prompt=result.prompt,
        timings=InspectTimings(**vars(result.timings)),
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
