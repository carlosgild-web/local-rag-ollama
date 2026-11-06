"""Ollama model management and health: list, pull (streamed), delete, ping.

Takes an optional httpx transport so tests can mock Ollama with
httpx.MockTransport instead of needing it running.
"""

import json
from collections.abc import Iterator

import httpx


class OllamaAdmin:
    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
    ):
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"), transport=transport, timeout=timeout
        )

    def ping(self) -> str:
        """Returns the Ollama version; raises httpx.HTTPError when unreachable."""
        response = self._client.get("/api/version")
        response.raise_for_status()
        return response.json().get("version", "unknown")

    def list_models(self) -> list[dict]:
        response = self._client.get("/api/tags")
        response.raise_for_status()
        return [
            {
                "name": model["name"],
                "size": model.get("size"),
                "modified_at": model.get("modified_at"),
                "family": model.get("details", {}).get("family"),
                "parameter_size": model.get("details", {}).get("parameter_size"),
                "capabilities": self.capabilities(model["name"]),
            }
            for model in response.json().get("models", [])
        ]

    def capabilities(self, name: str) -> list[str]:
        """What a model can do, from /api/show: e.g. ["embedding"] or
        ["completion", "tools"]. Empty if Ollama doesn't say."""
        try:
            response = self._client.post("/api/show", json={"model": name})
            response.raise_for_status()
        except httpx.HTTPError:
            return []
        return list(response.json().get("capabilities") or [])

    def loaded_models(self) -> list[str]:
        """Models Ollama currently holds in memory (/api/ps)."""
        response = self._client.get("/api/ps")
        response.raise_for_status()
        return [m["name"] for m in response.json().get("models", [])]

    def pull(self, name: str) -> Iterator[dict]:
        """Yields Ollama's progress objects ({status, total?, completed?})."""
        with self._client.stream(
            "POST", "/api/pull", json={"model": name, "stream": True}, timeout=None
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    yield json.loads(line)

    def delete(self, name: str) -> bool:
        """Returns False when the model doesn't exist."""
        response = self._client.request("DELETE", "/api/delete", json={"model": name})
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return True
