"""Hybrid retrieval: vector search + FTS5, fused with Reciprocal Rank Fusion.

See PLAN.md section 6: 20 candidates from each of vector search and FTS5,
fused, of which `top_k` are sent to the LLM. Only chunks of each
document's *active* version, in the given collection, of non-trashed
documents are eligible: older versions stay indexed (invariant 3) but are
filtered out here.

`retrieve_many` searches several shelves at once (the employee portal,
decision 0010). Each shelf is searched with its own embedding model, so
vectors from different models are never compared (invariant 4); the
per-shelf candidate lists are fused by rank, which RRF needs anyway.
"""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.fts import build_match_query
from app.db.models import Chunk, Collection, Document, DocumentVersion
from app.llm.base import EmbeddingClient
from app.retrieval.fusion import fuse_rrf_scored
from app.retrieval.vector_store import VectorStore

# Chroma can't filter on "is this the active version" (that changes on
# rollback without touching vectors), so over-fetch and filter in SQLite.
VECTOR_OVERFETCH = 3


@dataclass
class RetrievedChunk:
    chunk_id: int
    text: str
    page: int | None
    heading: str | None
    filename: str
    document_id: int
    version_id: int | None = None
    score: float = 0.0


def retrieve(
    db: Session,
    question: str,
    *,
    collection: Collection,
    settings: Settings,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    return retrieve_many(
        db,
        question,
        collections=[collection],
        settings=settings,
        embedding_client_for=lambda _model: embedding_client,
        vector_store=vector_store,
        top_k=top_k,
    )


def retrieve_many(
    db: Session,
    question: str,
    *,
    collections: list[Collection],
    settings: Settings,
    embedding_client_for: Callable[[str], EmbeddingClient],
    vector_store: VectorStore,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    """Hybrid retrieval over one or more shelves. With one shelf this is
    exactly the single-shelf search: its vector and FTS lists, fused."""
    top_k = top_k or settings.retrieval_top_k
    candidates = settings.retrieval_candidates

    embeddings: dict[str, list[float]] = {}  # the question, once per model

    def embed(model: str) -> list[float]:
        if model not in embeddings:
            [embeddings[model]] = embedding_client_for(model).embed([question])
        return embeddings[model]

    ranked_lists: list[list[int]] = []
    for collection in collections:
        ranked_lists.append(_vector_candidate_ids(db, collection, embed, vector_store, candidates))
        ranked_lists.append(_fts_candidate_ids(db, question, collection, candidates))

    fused = fuse_rrf_scored(ranked_lists)[:top_k]
    if not fused:
        return []

    rows = _fetch_chunks(db, [chunk_id for chunk_id, _ in fused])
    results = []
    for chunk_id, score in fused:
        if chunk_id not in rows:
            continue
        chunk, filename, document_id = rows[chunk_id]
        results.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                text=chunk.text,
                page=chunk.page,
                heading=chunk.heading,
                filename=filename,
                document_id=document_id,
                version_id=chunk.version_id,
                score=score,
            )
        )
    return results


def _eligible(collection: Collection):
    """SQL conditions for a chunk that may be served from `collection`."""
    return (
        Chunk.collection_id == collection.id,
        Chunk.retired_at.is_(None),
        Document.active_version_id == Chunk.version_id,
        Document.trashed_at.is_(None),
    )


def _vector_candidate_ids(
    db: Session,
    collection: Collection,
    embed: Callable[[str], list[float]],
    vector_store: VectorStore,
    candidates: int,
) -> list[int]:
    if vector_store.count(collection.chroma_collection) == 0:
        return []
    embedding = embed(collection.embedding_model)
    matches = vector_store.query(
        collection.chroma_collection, embedding, candidates * VECTOR_OVERFETCH
    )
    ranked = [int(match.id.split(":", 1)[1]) for match in matches]
    if not ranked:
        return []

    eligible = set(
        db.execute(
            select(Chunk.id)
            .join(DocumentVersion, DocumentVersion.id == Chunk.version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(Chunk.id.in_(ranked), *_eligible(collection))
        )
        .scalars()
        .all()
    )
    return [chunk_id for chunk_id in ranked if chunk_id in eligible][:candidates]


def _fts_candidate_ids(
    db: Session, question: str, collection: Collection, candidates: int
) -> list[int]:
    match_query = build_match_query(question)
    if not match_query:
        return []
    rows = db.execute(
        text(
            "SELECT chunks.id FROM chunks_fts"
            " JOIN chunks ON chunks.id = chunks_fts.rowid"
            " JOIN document_versions ON document_versions.id = chunks.version_id"
            " JOIN documents ON documents.id = document_versions.document_id"
            " WHERE chunks_fts MATCH :q"
            " AND chunks.collection_id = :collection_id"
            " AND documents.active_version_id = chunks.version_id"
            " AND documents.trashed_at IS NULL"
            " ORDER BY chunks_fts.rank LIMIT :k"
        ),
        {"q": match_query, "collection_id": collection.id, "k": candidates},
    ).fetchall()
    return [row[0] for row in rows]


def _fetch_chunks(db: Session, chunk_ids: list[int]) -> dict[int, tuple[Chunk, str, int]]:
    rows = db.execute(
        select(Chunk, Document.filename, Document.id)
        .join(DocumentVersion, DocumentVersion.id == Chunk.version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(Chunk.id.in_(chunk_ids))
    ).all()
    return {chunk.id: (chunk, filename, document_id) for chunk, filename, document_id in rows}
