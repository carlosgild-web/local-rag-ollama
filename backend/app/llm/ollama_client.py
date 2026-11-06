"""Ollama-backed LLMClient and EmbeddingClient implementations."""

import json
from collections.abc import Iterator

import httpx

from app.llm.base import EmbeddingClient, LLMClient


class OllamaError(httpx.HTTPError):
    """Ollama answered with an error. Carries Ollama's own reason (for
    example an out-of-memory model load) instead of a bare status code."""

    def __init__(self, status_code: int | None, reason: str, model: str):
        super().__init__(f"Ollama error ({status_code or 'stream'}) for {model}: {reason}")
        self.status_code = status_code
        self.reason = reason
        self.model = model

    @property
    def out_of_memory(self) -> bool:
        text = self.reason.lower()
        return "out of memory" in text or "out-of-memory" in text or "failed to allocate" in text


def _check(response: httpx.Response, model: str) -> None:
    if response.is_success:
        return
    response.read()  # streamed responses need the body read first
    try:
        reason = response.json().get("error") or response.text
    except ValueError:
        reason = response.text
    raise OllamaError(response.status_code, reason.strip() or response.reason_phrase, model)


class OllamaLLMClient(LLMClient):
    def __init__(self, base_url: str, model: str, timeout: float = 300.0):
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
        _check(response, self._model)
        return response.json()["response"]

    def stream_generate(
        self, prompt: str, *, temperature: float = 0.2, num_ctx: int = 8192
    ) -> Iterator[str]:
        with httpx.stream(
            "POST",
            f"{self._base_url}/api/generate",
            json={
                "model": self._model,
                "prompt": prompt,
                "stream": True,
                "options": {"temperature": temperature, "num_ctx": num_ctx},
            },
            timeout=self._timeout,
        ) as response:
            _check(response, self._model)
            for line in response.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if data.get("error"):  # Ollama can fail mid-stream too
                    raise OllamaError(None, data["error"], self._model)
                if data.get("response"):
                    yield data["response"]
                if data.get("done"):
                    break


class OllamaEmbeddingClient(EmbeddingClient):
    def __init__(self, base_url: str, model: str, timeout: float = 300.0):
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
        _check(response, self._model)
        embeddings = response.json()["embeddings"]
        if embeddings:
            self._dimensions = len(embeddings[0])
        return embeddings

    @property
    def dimensions(self) -> int:
        if self._dimensions is None:
            self._dimensions = len(self.embed(["dimension probe"])[0])
        return self._dimensions
