from pathlib import Path

from app.core.config import Settings
from app.llm.fake_client import FakeEmbeddingClient, FakeLLMClient
from app.retrieval.fake_store import FakeVectorStore
from app.retrieval.prompt import NOT_FOUND_PHRASE
from app.retrieval.qa import answer_question, prepare_context
from app.versioning import service

CORPUS = Path(__file__).parent / "corpus"


def _setup(db, tmp_path, ingest_coffee=False):
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")
    vector_store = FakeVectorStore()
    collection = service.create_collection(db, vector_store, name="default", embedding_model="fake")
    embedder = FakeEmbeddingClient(dimensions=8)
    if ingest_coffee:
        service.ingest_document(
            db,
            collection=collection,
            source_path=CORPUS / "coffee-brewing-methods.txt",
            settings=settings,
            embedding_client=embedder,
            vector_store=vector_store,
        )
    return {
        "collection": collection,
        "settings": settings,
        "embedding_client": embedder,
        "vector_store": vector_store,
    }


def test_prepare_context_returns_none_for_empty_knowledge_base(db_session, tmp_path):
    kwargs = _setup(db_session, tmp_path)
    assert prepare_context(db_session, "anything", **kwargs) is None


def test_answer_question_returns_not_found_for_empty_knowledge_base(db_session, tmp_path):
    kwargs = _setup(db_session, tmp_path)
    llm_client = FakeLLMClient()

    answer = answer_question(db_session, "anything", llm_client=llm_client, **kwargs)

    assert answer == NOT_FOUND_PHRASE
    assert llm_client.calls == [], "the LLM must not be called when nothing is retrieved"


def test_answer_question_builds_prompt_and_appends_sources(db_session, tmp_path):
    kwargs = _setup(db_session, tmp_path, ingest_coffee=True)
    llm_client = FakeLLMClient(responses=["Espresso uses high pressure. [1]"])

    answer = answer_question(db_session, "How does espresso work?", llm_client=llm_client, **kwargs)

    assert "Espresso uses high pressure. [1]" in answer
    assert "Sources:" in answer
    assert "coffee-brewing-methods.txt" in answer
    assert len(llm_client.calls) == 1
    assert "espresso" in llm_client.calls[0].lower()


def test_prepare_context_uses_profile_instructions(db_session, tmp_path):
    kwargs = _setup(db_session, tmp_path, ingest_coffee=True)
    context = prepare_context(db_session, "espresso", system_instructions="CUSTOM RULES", **kwargs)
    assert context.prompt.startswith("CUSTOM RULES")
