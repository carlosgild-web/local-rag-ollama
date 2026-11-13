"""Question answering: retrieve, build the grounded prompt, generate.

The single service layer for `ask` — the CLI and the chat API call into
this module rather than wiring retrieval + prompting themselves.
"""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Collection
from app.llm.base import EmbeddingClient, LLMClient
from app.retrieval.glossary import expand_with_glossary
from app.retrieval.prompt import NOT_FOUND_PHRASE, build_prompt, format_sources
from app.retrieval.reranker import NoOpReranker, Reranker
from app.retrieval.retrieve import RetrievedChunk, retrieve, retrieve_many
from app.retrieval.vector_store import VectorStore


@dataclass
class AnswerContext:
    prompt: str
    chunks: list[RetrievedChunk]


def prepare_context(
    db: Session,
    question: str,
    *,
    collection: Collection,
    settings: Settings,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    top_k: int | None = None,
    system_instructions: str | None = None,
    reranker: Reranker | None = None,
) -> AnswerContext | None:
    """Returns None when there is nothing to retrieve (empty knowledge base).
    The question is expanded with the glossary for both search and prompt."""
    question = expand_with_glossary(db, question)
    chunks = retrieve(
        db,
        question,
        collection=collection,
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
        top_k=top_k,
    )
    return _context(question, chunks, settings, system_instructions, reranker)


def prepare_context_many(
    db: Session,
    question: str,
    *,
    collections: list[Collection],
    settings: Settings,
    embedding_client_for: Callable[[str], EmbeddingClient],
    vector_store: VectorStore,
    top_k: int | None = None,
    system_instructions: str | None = None,
    reranker: Reranker | None = None,
) -> AnswerContext | None:
    """Like `prepare_context`, searching several shelves (the employee portal)."""
    question = expand_with_glossary(db, question)
    chunks = retrieve_many(
        db,
        question,
        collections=collections,
        settings=settings,
        embedding_client_for=embedding_client_for,
        vector_store=vector_store,
        top_k=top_k,
    )
    return _context(question, chunks, settings, system_instructions, reranker)


def _context(
    question: str,
    chunks: list[RetrievedChunk],
    settings: Settings,
    system_instructions: str | None,
    reranker: Reranker | None,
) -> AnswerContext | None:
    if not chunks:
        return None

    if settings.rerank_enabled:
        chunks = (reranker or NoOpReranker()).rerank(question, chunks)

    return AnswerContext(prompt=build_prompt(question, chunks, system_instructions), chunks=chunks)


def answer_question(
    db: Session,
    question: str,
    *,
    collection: Collection,
    settings: Settings,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    llm_client: LLMClient,
) -> str:
    """Non-streaming answer with a trailing Sources section. Mainly for tests;
    the CLI and chat API use `prepare_context` directly so they can stream."""
    context = prepare_context(
        db,
        question,
        collection=collection,
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )
    if context is None:
        return NOT_FOUND_PHRASE

    answer = llm_client.generate(
        context.prompt, temperature=settings.llm_temperature, num_ctx=settings.ollama_num_ctx
    )
    return f"{answer}\n\nSources:\n{format_sources(context.chunks)}"
