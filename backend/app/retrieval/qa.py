"""Question answering: retrieve, build the grounded prompt, generate.

The single service layer for `ask` — the CLI (and later the API) call
into this module rather than wiring retrieval + prompting themselves.
"""

from dataclasses import dataclass

from app.core.config import Settings
from app.ingest.pipeline import DEFAULT_COLLECTION
from app.llm.base import EmbeddingClient, LLMClient
from app.retrieval.prompt import NOT_FOUND_PHRASE, build_prompt, format_sources
from app.retrieval.reranker import NoOpReranker, Reranker
from app.retrieval.retrieve import RetrievedChunk, retrieve
from app.retrieval.vector_store import VectorStore


@dataclass
class AnswerContext:
    prompt: str
    chunks: list[RetrievedChunk]


def prepare_context(
    question: str,
    *,
    settings: Settings,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    reranker: Reranker | None = None,
    collection: str = DEFAULT_COLLECTION,
) -> AnswerContext | None:
    """Returns None when there is nothing to retrieve (empty knowledge base)."""
    chunks = retrieve(
        question,
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
        collection=collection,
    )
    if not chunks:
        return None

    if settings.rerank_enabled:
        chunks = (reranker or NoOpReranker()).rerank(question, chunks)

    return AnswerContext(prompt=build_prompt(question, chunks), chunks=chunks)


def answer_question(
    question: str,
    *,
    settings: Settings,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    llm_client: LLMClient,
    collection: str = DEFAULT_COLLECTION,
) -> str:
    """Non-streaming answer with a trailing Sources section. Mainly for tests;
    the CLI uses `prepare_context` directly so it can stream the answer."""
    context = prepare_context(
        question,
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
        collection=collection,
    )
    if context is None:
        return NOT_FOUND_PHRASE

    answer = llm_client.generate(
        context.prompt, temperature=settings.llm_temperature, num_ctx=settings.ollama_num_ctx
    )
    return f"{answer}\n\nSources:\n{format_sources(context.chunks)}"
