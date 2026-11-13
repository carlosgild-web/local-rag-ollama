"""Composition root: builds the long-lived objects the API, CLI, and job
worker share. Tests build a Runtime from fakes instead (tests/conftest.py)."""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.migrate import upgrade_to_head
from app.db.session import make_engine, make_session_factory
from app.llm.base import EmbeddingClient, LLMClient
from app.llm.ollama_admin import OllamaAdmin
from app.retrieval.reranker import Reranker
from app.retrieval.vector_store import VectorStore


@dataclass
class Runtime:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    vector_store: VectorStore
    # Keyed by model name: a collection's embedding model, a profile's chat model.
    embedding_client_for: Callable[[str], EmbeddingClient]
    llm_client_for: Callable[[str], LLMClient]
    ollama: OllamaAdmin
    # Loads its model on first use (decision 0023); None in tests unless set.
    reranker: Reranker | None = None


def build_runtime(settings: Settings) -> Runtime:
    """Real runtime: migrates SQLite to head, opens Chroma, talks to Ollama."""
    # Imported here so test runs never import chromadb unless they need it.
    from app.llm.ollama_client import OllamaEmbeddingClient, OllamaLLMClient
    from app.retrieval.chroma_store import ChromaVectorStore
    from app.retrieval.onnx_reranker import OnnxReranker

    settings.ensure_data_dirs()
    upgrade_to_head(settings.db_path)
    engine = make_engine(settings.db_path)

    embedding_clients: dict[str, EmbeddingClient] = {}
    llm_clients: dict[str, LLMClient] = {}

    def embedding_client_for(model: str) -> EmbeddingClient:
        if model not in embedding_clients:
            embedding_clients[model] = OllamaEmbeddingClient(settings.ollama_base_url, model)
        return embedding_clients[model]

    def llm_client_for(model: str) -> LLMClient:
        if model not in llm_clients:
            llm_clients[model] = OllamaLLMClient(settings.ollama_base_url, model)
        return llm_clients[model]

    return Runtime(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        vector_store=ChromaVectorStore(settings.chroma_dir),
        embedding_client_for=embedding_client_for,
        llm_client_for=llm_client_for,
        ollama=OllamaAdmin(settings.ollama_base_url),
        reranker=OnnxReranker(settings.reranker_dir),
    )
