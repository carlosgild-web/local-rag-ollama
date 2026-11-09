"""The real Chroma store must never phone home: no cloud calls at runtime."""

from app.retrieval.chroma_store import ChromaVectorStore


def test_chroma_telemetry_is_off(tmp_path):
    store = ChromaVectorStore(tmp_path / "chroma")
    assert store._client.get_settings().anonymized_telemetry is False
