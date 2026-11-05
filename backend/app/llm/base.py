"""Abstract interfaces for chat and embedding clients.

Real implementations call Ollama; fake implementations are deterministic
and used by unit tests / CI so they never need Ollama running.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator


class LLMClient(ABC):
    @abstractmethod
    def generate(self, prompt: str, *, temperature: float = 0.2, num_ctx: int = 8192) -> str:
        """Generate a single completion for `prompt`."""

    @abstractmethod
    def stream_generate(
        self, prompt: str, *, temperature: float = 0.2, num_ctx: int = 8192
    ) -> Iterator[str]:
        """Generate a completion for `prompt`, yielding text fragments as produced."""


class EmbeddingClient(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, same order."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Vector dimensionality produced by this client."""
