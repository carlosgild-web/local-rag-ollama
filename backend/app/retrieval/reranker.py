"""Reranker hook point.

Off by default in the MVP (PLAN.md section 6: "Reranker | Off in MVP.
Later, bge-reranker-v2-m3 rescoring the top 20"). NoOpReranker is the only
implementation for now; a real cross-encoder reranker plugs in here later
behind the same interface, gated by `settings.rerank_enabled`.
"""

from abc import ABC, abstractmethod

from app.retrieval.retrieve import RetrievedChunk


class Reranker(ABC):
    @abstractmethod
    def rerank(self, question: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]: ...


class NoOpReranker(Reranker):
    def rerank(self, question: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return chunks
