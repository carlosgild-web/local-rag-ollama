"""Abstract VectorStore interface.

Collections carry the embedding model name and chunking config as metadata
(see CLAUDE.md invariant 4) so vectors from different models are never mixed.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class VectorMatch:
    id: str
    score: float
    metadata: dict
    document: str


class VectorStore(ABC):
    @abstractmethod
    def get_or_create_collection(self, name: str, metadata: dict) -> None:
        """Create the collection if missing; metadata should include at least
        `embedding_model` and chunking config so mixed vectors are refused."""

    @abstractmethod
    def upsert(
        self,
        collection: str,
        ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
        documents: list[str],
    ) -> None: ...

    @abstractmethod
    def query(self, collection: str, embedding: list[float], top_k: int) -> list[VectorMatch]: ...

    @abstractmethod
    def delete(self, collection: str, ids: list[str]) -> None: ...

    @abstractmethod
    def count(self, collection: str) -> int: ...
