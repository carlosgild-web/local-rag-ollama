"""In-memory VectorStore for tests, no Chroma/disk needed."""

import math

from app.retrieval.vector_store import VectorMatch, VectorStore


class FakeVectorStore(VectorStore):
    def __init__(self):
        self._collections: dict[str, dict] = {}
        self._metadata: dict[str, dict] = {}

    def get_or_create_collection(self, name: str, metadata: dict) -> None:
        if name not in self._collections:
            self._collections[name] = {}
            self._metadata[name] = metadata
            return

        existing_model = self._metadata[name].get("embedding_model")
        requested_model = metadata.get("embedding_model")
        if existing_model and requested_model and existing_model != requested_model:
            raise ValueError(f"Collection '{name}' already uses embedding model '{existing_model}'")

    def upsert(
        self,
        collection: str,
        ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
        documents: list[str],
    ) -> None:
        store = self._collections[collection]
        for chunk_id, embedding, metadata, document in zip(
            ids, embeddings, metadatas, documents, strict=True
        ):
            store[chunk_id] = (embedding, metadata, document)

    def query(self, collection: str, embedding: list[float], top_k: int) -> list[VectorMatch]:
        store = self._collections.get(collection, {})
        scored = [
            VectorMatch(id=chunk_id, score=_cosine(embedding, vec), metadata=meta, document=doc)
            for chunk_id, (vec, meta, doc) in store.items()
        ]
        scored.sort(key=lambda m: m.score, reverse=True)
        return scored[:top_k]

    def delete(self, collection: str, ids: list[str]) -> None:
        store = self._collections.get(collection, {})
        for chunk_id in ids:
            store.pop(chunk_id, None)

    def count(self, collection: str) -> int:
        return len(self._collections.get(collection, {}))

    def ping(self) -> None:
        if getattr(self, "fail_ping", False):
            raise RuntimeError("fake vector store is down")


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
    norm_b = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (norm_a * norm_b)
