"""Hybrid retrieval: vector search + FTS5, fused with Reciprocal Rank Fusion.

See PLAN.md section 6: 20 candidates from each of vector search and FTS5,
fused, of which `top_k` are sent to the LLM. Only chunks of each
document's *active* version, in the given collection, of non-trashed
documents are eligible: older versions stay indexed (invariant 3) but are
filtered out here.

`retrieve_many` searches several shelves at once (the employee portal,
decision 0010). Scores are only compared where they mean the same thing:
- shelves that share an embedding model give one vector list, merged by
  cosine similarity;
- FTS5 runs once over all the shelves (one index, one BM25 ranking);
- RRF then fuses those lists by rank, so vectors from different models are
  never compared (invariant 4).
Merging per shelf instead would put every shelf's best chunk near the top,
however weak: a one-document shelf would win a slot for every question.

`mode` keeps only one side, for the evaluation's comparison (decision 0019):
"vector" skips FTS5 and "keyword" skips the vectors. Chat always uses hybrid.
"""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import bindparam, select, text
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

RETRIEVAL_MODES = ("hybrid", "vector", "keyword")


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
    mode: str = "hybrid",
) -> list[RetrievedChunk]:
    return retrieve_many(
        db,
        question,
        collections=[collection],
        settings=settings,
        embedding_client_for=lambda _model: embedding_client,
        vector_store=vector_store,
        top_k=top_k,
        mode=mode,
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
    mode: str = "hybrid",
) -> list[RetrievedChunk]:
    """Hybrid retrieval over one or more shelves. With one shelf this is
    exactly the single-shelf search: its vector and FTS lists, fused."""
    if mode not in RETRIEVAL_MODES:
        raise ValueError(f"unknown retrieval mode {mode!r}")
    top_k = top_k or settings.retrieval_top_k
    candidates = settings.retrieval_candidates

    embeddings: dict[str, list[float]] = {}  # the question, once per model

    def embed(model: str) -> list[float]:
        if model not in embeddings:
            [embeddings[model]] = embedding_client_for(model).embed([question])
        return embeddings[model]

    by_model: dict[str, list[Collection]] = {}
    for collection in collections:
        by_model.setdefault(collection.embedding_model, []).append(collection)

    ranked_lists = []
    if mode != "keyword":
        ranked_lists += [
            _vector_candidate_ids(db, shelves, lambda m=model: embed(m), vector_store, candidates)
            for model, shelves in by_model.items()
        ]
    if mode != "vector":
        ranked_lists.append(_fts_candidate_ids(db, question, collections, candidates))

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


def _eligible(collections: list[Collection]):
    """SQL conditions for a chunk that may be served from these shelves."""
    return (
        Chunk.collection_id.in_([c.id for c in collections]),
        Chunk.retired_at.is_(None),
        Document.active_version_id == Chunk.version_id,
        Document.trashed_at.is_(None),
    )


def _vector_candidate_ids(
    db: Session,
    collections: list[Collection],
    embed: Callable[[], list[float]],
    vector_store: VectorStore,
    candidates: int,
) -> list[int]:
    """One ranked list for shelves that share an embedding model, merged by
    cosine similarity (comparable, since the model is the same)."""
    shelves = [c for c in collections if vector_store.count(c.chroma_collection) > 0]
    if not shelves:
        return []
    embedding = embed()
    scored: dict[int, float] = {}
    for collection in shelves:
        for match in vector_store.query(
            collection.chroma_collection, embedding, candidates * VECTOR_OVERFETCH
        ):
            scored[int(match.id.split(":", 1)[1])] = match.score
    if not scored:
        return []

    eligible = set(
        db.execute(
            select(Chunk.id)
            .join(DocumentVersion, DocumentVersion.id == Chunk.version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(Chunk.id.in_(list(scored)), *_eligible(shelves))
        )
        .scalars()
        .all()
    )
    ranked = sorted(eligible, key=lambda chunk_id: scored[chunk_id], reverse=True)
    return ranked[:candidates]


def _fts_candidate_ids(
    db: Session, question: str, collections: list[Collection], candidates: int
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
            " AND chunks.collection_id IN :collection_ids"
            " AND documents.active_version_id = chunks.version_id"
            " AND documents.trashed_at IS NULL"
            " ORDER BY chunks_fts.rank LIMIT :k"
        ).bindparams(bindparam("collection_ids", expanding=True)),
        {"q": match_query, "collection_ids": [c.id for c in collections], "k": candidates},
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
