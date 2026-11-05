import pytest

from app.llm.fake_client import FakeEmbeddingClient, FakeLLMClient
from app.retrieval.fake_store import FakeVectorStore


def test_fake_embedding_is_deterministic():
    client = FakeEmbeddingClient(dimensions=8)
    a1 = client.embed(["hello"])[0]
    a2 = client.embed(["hello"])[0]
    assert a1 == a2
    assert len(a1) == 8


def test_fake_embedding_differs_for_different_text():
    client = FakeEmbeddingClient(dimensions=8)
    a = client.embed(["hello"])[0]
    b = client.embed(["goodbye"])[0]
    assert a != b


def test_fake_llm_returns_queued_responses_then_echoes():
    client = FakeLLMClient(responses=["first"])
    assert client.generate("prompt 1") == "first"
    echoed = client.generate("prompt 2")
    assert "prompt 2" in echoed
    assert client.calls == ["prompt 1", "prompt 2"]


def test_fake_vector_store_upsert_and_query_roundtrip():
    store = FakeVectorStore()
    store.get_or_create_collection("docs", metadata={"embedding_model": "fake"})
    store.upsert(
        "docs",
        ids=["a", "b"],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
        metadatas=[{"n": 1}, {"n": 2}],
        documents=["doc a", "doc b"],
    )
    assert store.count("docs") == 2

    results = store.query("docs", embedding=[1.0, 0.0], top_k=1)
    assert len(results) == 1
    assert results[0].id == "a"
    assert results[0].document == "doc a"


def test_fake_vector_store_refuses_mismatched_embedding_model():
    store = FakeVectorStore()
    store.get_or_create_collection("docs", metadata={"embedding_model": "model-a"})
    with pytest.raises(ValueError):
        store.get_or_create_collection("docs", metadata={"embedding_model": "model-b"})


def test_fake_vector_store_delete():
    store = FakeVectorStore()
    store.get_or_create_collection("docs", metadata={"embedding_model": "fake"})
    store.upsert("docs", ids=["a"], embeddings=[[1.0]], metadatas=[{}], documents=["doc a"])
    store.delete("docs", ["a"])
    assert store.count("docs") == 0
