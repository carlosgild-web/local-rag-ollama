"""Ollama-backed LLMClient and EmbeddingClient implementations."""

import httpx

from app.llm.base import EmbeddingClient, LLMClient


class OllamaLLMClient(LLMClient):
    def __init__(self, base_url: str, model: str, timeout: float = 120.0):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def generate(self, prompt: str, *, temperature: float = 0.2, num_ctx: int = 8192) -> str:
        response = httpx.post(
            f"{self._base_url}/api/generate",
            json={
                "model": self._model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature, "num_ctx": num_ctx},
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()["response"]


class OllamaEmbeddingClient(EmbeddingClient):
    def __init__(self, base_url: str, model: str, timeout: float = 120.0):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._dimensions: int | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = httpx.post(
            f"{self._base_url}/api/embed",
            json={"model": self._model, "input": texts},
            timeout=self._timeout,
        )
        response.raise_for_status()
        embeddings = response.json()["embeddings"]
        if embeddings:
            self._dimensions = len(embeddings[0])
        return embeddings

    @property
    def dimensions(self) -> int:
        if self._dimensions is None:
            self._dimensions = len(self.embed(["dimension probe"])[0])
        return self._dimensions
