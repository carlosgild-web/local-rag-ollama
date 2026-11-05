from pathlib import Path

from app.core.config import Settings
from app.ingest.pipeline import ingest_path
from app.llm.fake_client import FakeEmbeddingClient, FakeLLMClient
from app.retrieval.fake_store import FakeVectorStore
from app.retrieval.prompt import NOT_FOUND_PHRASE
from app.retrieval.qa import answer_question, prepare_context

CORPUS = Path(__file__).parent / "corpus"


def _settings(tmp_path) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path / "data")


def test_prepare_context_returns_none_for_empty_knowledge_base(tmp_path):
    settings = _settings(tmp_path)
    context = prepare_context(
        "anything",
        settings=settings,
        embedding_client=FakeEmbeddingClient(dimensions=8),
        vector_store=FakeVectorStore(),
    )
    assert context is None


def test_answer_question_returns_not_found_for_empty_knowledge_base(tmp_path):
    settings = _settings(tmp_path)
    llm_client = FakeLLMClient()

    answer = answer_question(
        "anything",
        settings=settings,
        embedding_client=FakeEmbeddingClient(dimensions=8),
        vector_store=FakeVectorStore(),
        llm_client=llm_client,
    )

    assert answer == NOT_FOUND_PHRASE
    assert llm_client.calls == [], "the LLM should never be called when there's nothing to retrieve"


def test_answer_question_builds_prompt_and_appends_sources(tmp_path):
    settings = _settings(tmp_path)
    embedding_client = FakeEmbeddingClient(dimensions=8)
    vector_store = FakeVectorStore()
    llm_client = FakeLLMClient(responses=["Espresso uses high pressure. [1]"])

    ingest_path(
        CORPUS / "coffee-brewing-methods.txt",
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )

    answer = answer_question(
        "How does espresso work?",
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
        llm_client=llm_client,
    )

    assert "Espresso uses high pressure. [1]" in answer
    assert "Sources:" in answer
    assert "coffee-brewing-methods.txt" in answer
    assert len(llm_client.calls) == 1
    assert "espresso" in llm_client.calls[0].lower()
