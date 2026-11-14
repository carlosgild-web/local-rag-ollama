"""The retrieval inspector (PLAN.md Phase 6, decision 0024).

Runs the chat's retrieval with adjustable parameters and explains the
result: every fused candidate with its vector and keyword ranks and scores,
which ones would be sent to the model, the exact prompt, and how long each
step took. It only reads; nothing is stored, so nothing is audited.

With the default parameters the chunks sent and the prompt are the ones the
console chat would use for the same question, shelf and profile.
"""

import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Collection, RagProfile
from app.llm.base import EmbeddingClient
from app.retrieval.glossary import expand_with_glossary
from app.retrieval.prompt import build_prompt
from app.retrieval.reranker import Reranker
from app.retrieval.retrieve import RetrievedChunk, retrieve_many
from app.retrieval.vector_store import VectorStore


class QuestionEmbeddingCache:
    """The last few question embeddings, so moving a slider doesn't embed the
    same question again (an Ollama round trip each time). Bounded LRU."""

    def __init__(self, max_entries: int = 64):
        self.max_entries = max_entries
        self._entries: OrderedDict[tuple[str, str], list[float]] = OrderedDict()

    def get(self, model: str, text: str) -> list[float] | None:
        key = (model, text)
        if key in self._entries:
            self._entries.move_to_end(key)
            return self._entries[key]
        return None

    def put(self, model: str, text: str, vector: list[float]) -> None:
        self._entries[(model, text)] = vector
        self._entries.move_to_end((model, text))
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)


class _CachedEmbedding(EmbeddingClient):
    """Wraps a model's client with the cache, and times real embedding calls."""

    def __init__(self, inner: EmbeddingClient, model: str, cache: QuestionEmbeddingCache, timer):
        self._inner, self._model, self._cache, self._timer = inner, model, cache, timer

    @property
    def dimensions(self) -> int:
        return self._inner.dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float] | None] = [self._cache.get(self._model, t) for t in texts]
        missing = [t for t, v in zip(texts, out, strict=True) if v is None]
        if missing:
            start = time.perf_counter()
            vectors = self._inner.embed(missing)
            self._timer.embed_ms += (time.perf_counter() - start) * 1000
            fresh = dict(zip(missing, vectors, strict=True))
            for t, v in fresh.items():
                self._cache.put(self._model, t, v)
            out = [v if v is not None else fresh[t] for t, v in zip(texts, out, strict=True)]
        else:
            self._timer.embedding_cached = True
        return out  # type: ignore[return-value]


@dataclass
class Timings:
    embed_ms: float = 0.0
    embedding_cached: bool = False
    search_ms: float = 0.0  # vector + keyword search and fusion, without embedding
    rerank_ms: float | None = None
    total_ms: float = 0.0


@dataclass
class InspectedChunk:
    chunk: RetrievedChunk
    rank: int
    sent: bool  # among the top-k the model would see
    rerank_score: float | None = None


@dataclass
class InspectResult:
    question: str
    expanded_question: str  # after the glossary; what search and prompt use
    collection_ids: list[int]
    profile: RagProfile
    parameters: dict
    chunks: list[InspectedChunk] = field(default_factory=list)
    prompt: str | None = None
    timings: Timings = field(default_factory=Timings)


def inspect_retrieval(
    db: Session,
    question: str,
    *,
    collections: list[Collection],
    profile: RagProfile,
    settings: Settings,
    embedding_client_for: Callable[[str], EmbeddingClient],
    vector_store: VectorStore,
    cache: QuestionEmbeddingCache,
    mode: str = "hybrid",
    top_k: int | None = None,
    candidates: int | None = None,
    vector_weight: float = 0.5,
    min_cosine: float = 0.0,
    reranker: Reranker | None = None,
    include_prompt: bool = True,
) -> InspectResult:
    """`top_k` defaults to the profile's; `candidates` to the settings' (per
    side, and also how many fused candidates are shown and reranked)."""
    started = time.perf_counter()
    top_k = top_k or profile.retrieval_top_k
    candidates = candidates or settings.retrieval_candidates
    timings = Timings()
    expanded = expand_with_glossary(db, question)

    def cached_client(model: str) -> EmbeddingClient:
        return _CachedEmbedding(embedding_client_for(model), model, cache, timings)

    start = time.perf_counter()
    # All fused candidates (as the chat fetches for its reranker), so the
    # page can show what falls just below the top-k line.
    chunks = retrieve_many(
        db,
        expanded,
        collections=collections,
        settings=settings,
        embedding_client_for=cached_client,
        vector_store=vector_store,
        top_k=candidates,
        mode=mode,
        candidates=candidates,
        vector_weight=vector_weight,
        min_cosine=min_cosine,
    )
    timings.search_ms = (time.perf_counter() - start) * 1000 - timings.embed_ms

    rerank_scores: dict[int, float] = {}
    if reranker is not None and chunks:
        start = time.perf_counter()
        reranked = reranker.rerank(expanded, chunks)
        timings.rerank_ms = (time.perf_counter() - start) * 1000
        rerank_scores = {c.chunk_id: c.score for c in reranked}
        # The fused score stays visible next to the reranker's.
        by_id = {c.chunk_id: c for c in chunks}
        chunks = [replace(by_id[c.chunk_id], score=c.score) for c in reranked]

    inspected = [
        InspectedChunk(
            chunk=chunk,
            rank=rank,
            sent=rank <= top_k,
            rerank_score=rerank_scores.get(chunk.chunk_id),
        )
        for rank, chunk in enumerate(chunks, start=1)
    ]
    sent = [i.chunk for i in inspected if i.sent]
    prompt = (
        build_prompt(expanded, sent, profile.system_prompt) if include_prompt and sent else None
    )
    timings.total_ms = (time.perf_counter() - started) * 1000
    return InspectResult(
        question=question,
        expanded_question=expanded,
        collection_ids=[c.id for c in collections],
        profile=profile,
        parameters={
            "mode": mode,
            "top_k": top_k,
            "candidates": candidates,
            "vector_weight": vector_weight,
            "min_cosine": min_cosine,
            "rerank": reranker is not None,
        },
        chunks=inspected,
        prompt=prompt,
        timings=timings,
    )
