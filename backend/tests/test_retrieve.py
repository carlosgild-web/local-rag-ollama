from pathlib import Path

from app.core.config import Settings
from app.ingest.pipeline import ingest_path
from app.llm.fake_client import FakeEmbeddingClient
from app.retrieval.fake_store import FakeVectorStore
from app.retrieval.retrieve import retrieve

CORPUS = Path(__file__).parent / "corpus"


def _settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None, data_dir=tmp_path / "data", retrieval_candidates=20, retrieval_top_k=5
    )


def test_retrieve_against_empty_knowledge_base_returns_nothing(tmp_path):
    settings = _settings(tmp_path)
    chunks = retrieve(
        "anything",
        settings=settings,
        embedding_client=FakeEmbeddingClient(dimensions=8),
        vector_store=FakeVectorStore(),
    )
    assert chunks == []


def test_retrieve_finds_keyword_match_via_fts(tmp_path):
    settings = _settings(tmp_path)
    embedding_client = FakeEmbeddingClient(dimensions=8)
    vector_store = FakeVectorStore()

    ingest_path(
        CORPUS / "coffee-brewing-methods.txt",
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )
    ingest_path(
        CORPUS / "intro-to-astronomy-telescopes.txt",
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )

    chunks = retrieve(
        "espresso",
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )

    assert chunks, "expected at least one match for a keyword from the coffee document"
    assert any("espresso" in c.text.lower() for c in chunks)
    assert all(c.filename for c in chunks)


def test_retrieve_respects_top_k(tmp_path):
    settings = _settings(tmp_path)
    settings = settings.model_copy(update={"retrieval_top_k": 1})
    embedding_client = FakeEmbeddingClient(dimensions=8)
    vector_store = FakeVectorStore()

    ingest_path(
        CORPUS / "basics-of-machine-learning.md",
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )

    chunks = retrieve(
        "machine learning",
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )
    assert len(chunks) <= 1
