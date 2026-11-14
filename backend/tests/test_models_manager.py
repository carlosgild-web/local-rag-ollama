"""The Models manager: what uses each model, and no deleting a model in use."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.versioning import service
from app.versioning.model_usage import same_model


@pytest.fixture
def client(runtime):
    app = create_app(runtime, start_worker=False)
    with TestClient(app) as test_client:
        yield test_client


def _models(client):
    return {m["name"]: m for m in client.get("/api/models").json()}


def test_names_compare_without_the_latest_tag():
    assert same_model("bge-m3") == same_model("bge-m3:latest") == same_model(" BGE-M3:latest ")
    assert same_model("qwen2.5:3b") != same_model("qwen2.5:7b")


def test_list_says_what_uses_each_model(client, runtime):
    client.get("/api/profiles")  # creates default v1, chatting with CHAT_MODEL (llama3.1)
    with runtime.session_factory() as db:
        service.create_collection(db, runtime.vector_store, name="hr", embedding_model="bge-m3")

    models = _models(client)
    assert models["llama3.1:latest"]["used_by"] == ["chat model of profile default v1"]
    assert models["bge-m3:latest"]["used_by"] == [
        "embedding model of shelf hr",
        "embedding model for new shelves (EMBEDDING_MODEL)",
    ]
    assert models["llama3.1:latest"]["loaded"] is False


def test_loaded_models_are_marked_and_ps_failures_are_ignored(client, runtime, monkeypatch):
    monkeypatch.setattr(runtime.ollama, "loaded_models", lambda: ["llama3.1:latest"])
    assert _models(client)["llama3.1:latest"]["loaded"] is True

    def broken():
        raise RuntimeError("ps failed")

    monkeypatch.setattr(runtime.ollama, "loaded_models", broken)
    assert _models(client)["llama3.1:latest"]["loaded"] is False


def test_a_model_in_use_cannot_be_deleted(client):
    client.get("/api/profiles")
    response = client.delete("/api/models/llama3.1:latest")
    assert response.status_code == 409
    assert "profile default v1" in response.json()["detail"]
    assert client.delete("/api/models/bge-m3:latest").status_code == 409, "EMBEDDING_MODEL"
    actions = {e["action"] for e in client.get("/api/audit").json()}
    assert "model_delete" not in actions


def test_switching_the_chat_model_frees_the_old_one(client):
    client.get("/api/profiles")
    client.post("/api/profiles", json={"chat_model": "qwen2.5:3b"})
    assert _models(client)["llama3.1:latest"]["used_by"] == []
    assert client.delete("/api/models/llama3.1:latest").status_code == 204
