"""Hybrid retrieval: vector search + FTS5, fused with Reciprocal Rank Fusion.

See PLAN.md section 6: 20 candidates from each of vector search and FTS5,
fused into a top-20 pool, of which `retrieval_top_k` are sent to the LLM.
"""

from dataclasses import dataclass

from app.core.config import Settings
from app.ingest import sqlite_store
from app.ingest.pipeline import DEFAULT_COLLECTION
from app.llm.base import EmbeddingClient
from app.retrieval.fusion import fuse_rrf
from app.retrieval.vector_store import VectorStore


@dataclass
class RetrievedChunk:
    chunk_id: int
    text: str
    page: int | None
    heading: str | None
    filename: str
    document_id: int


def retrieve(
    question: str,
    *,
    settings: Settings,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    collection: str = DEFAULT_COLLECTION,
) -> list[RetrievedChunk]:
    vector_store.get_or_create_collection(
        collection,
        metadata={
            "embedding_model": settings.embedding_model,
            "chunk_size_tokens": settings.chunk_size_tokens,
            "chunk_overlap_pct": settings.chunk_overlap_pct,
        },
    )

    conn = sqlite_store.connect(settings.db_path)
    try:
        vector_ids = _vector_candidate_ids(
            question, embedding_client, vector_store, collection, settings.retrieval_candidates
        )
        fts_ids = sqlite_store.search_fts(conn, question, settings.retrieval_candidates)

        fused_ids = fuse_rrf([vector_ids, fts_ids])
        top_ids = fused_ids[: settings.retrieval_top_k]
        if not top_ids:
            return []

        rows_by_id = sqlite_store.fetch_chunks(conn, top_ids)
        return [
            RetrievedChunk(
                chunk_id=chunk_id,
                text=rows_by_id[chunk_id]["text"],
                page=rows_by_id[chunk_id]["page"],
                heading=rows_by_id[chunk_id]["heading"],
                filename=rows_by_id[chunk_id]["filename"],
                document_id=rows_by_id[chunk_id]["document_id"],
            )
            for chunk_id in top_ids
            if chunk_id in rows_by_id
        ]
    finally:
        conn.close()


def _vector_candidate_ids(
    question: str,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    collection: str,
    top_k: int,
) -> list[int]:
    if vector_store.count(collection) == 0:
        return []
    [embedding] = embedding_client.embed([question])
    matches = vector_store.query(collection, embedding, top_k)
    chunk_ids = []
    for match in matches:
        _, chunk_id_str = match.id.split(":", 1)
        chunk_ids.append(int(chunk_id_str))
    return chunk_ids
