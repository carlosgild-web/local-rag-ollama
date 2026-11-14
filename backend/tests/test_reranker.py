"""The reranker (decision 0023): rescore the fused candidates, then cut to top-k."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.eval import service as eval_service
from app.main import create_app
from app.retrieval import onnx_reranker
from app.retrieval.qa import prepare_context
from app.retrieval.reranker import Reranker
from app.versioning import service

# The model the developer downloaded with `app.cli reranker-download`, if any.
LOCAL_MODEL = Path(__file__).resolve().parents[2] / "data" / "hf" / "bge-reranker-v2-m3-onnx"


class PreferWord(Reranker):
    """Puts passages containing `word` first; records what it was given."""

    def __init__(self, word: str):
        self.word = word
        self.seen: list[int] = []

    def rerank(self, question, chunks):
        self.seen.append(len(chunks))
        return sorted(chunks, key=lambda c: self.word not in c.text)


def _shelf_with_many_documents(runtime, db):
    shelf = service.create_collection(db, runtime.vector_store, name="s", embedding_model="fake")
    for i in range(12):
        text = f"Kiln note {i}: the kiln is checked weekly." + (" GOLDEN" if i == 11 else "")
        path = runtime.settings.uploads_dir / f"note{i}.txt"
        path.write_text(text, encoding="utf-8")
        service.ingest_document(
            db,
            collection=shelf,
            source_path=path,
            settings=runtime.settings,
            embedding_client=runtime.embedding_client_for("fake"),
            vector_store=runtime.vector_store,
        )
    return shelf


def _ask(runtime, db, shelf, settings, reranker):
    return prepare_context(
        db,
        "How often is the kiln checked?",
        collection=shelf,
        settings=settings,
        embedding_client=runtime.embedding_client_for("fake"),
        vector_store=runtime.vector_store,
        top_k=3,
        reranker=reranker,
    )


def test_reranking_rescores_all_candidates_then_keeps_top_k(runtime):
    settings = Settings(_env_file=None, data_dir=runtime.settings.data_dir, rerank_enabled=True)
    reranker = PreferWord("GOLDEN")
    with runtime.session_factory() as db:
        shelf = _shelf_with_many_documents(runtime, db)
        context = _ask(runtime, db, shelf, settings, reranker)
    assert reranker.seen == [12]  # every candidate, not just the top 3
    assert len(context.chunks) == 3
    assert "GOLDEN" in context.chunks[0].text


def test_reranker_is_ignored_when_turned_off(runtime):
    reranker = PreferWord("GOLDEN")
    with runtime.session_factory() as db:
        shelf = _shelf_with_many_documents(runtime, db)
        context = _ask(runtime, db, shelf, runtime.settings, reranker)  # rerank_enabled=False
    assert reranker.seen == [] and len(context.chunks) == 3


@pytest.fixture
def client(runtime):
    app = create_app(runtime, start_worker=False)
    with TestClient(app) as test_client:
        test_client.drain = app.state.worker.run_until_idle
        yield test_client


def _eval_set(client):
    shelf = client.post("/api/collections", json={"name": "ops"}).json()["id"]
    for name, text in (("a.txt", "Kiln checks happen weekly."), ("b.txt", "Kiln GOLDEN rule.")):
        client.post(
            "/api/documents",
            files=[("files", (name, text.encode(), "text/plain"))],
            data={"collection_id": str(shelf)},
        )
        client.drain()
    return client.post(
        "/api/eval/sets/import",
        json={"name": "s", "cases": [{"question": "kiln", "shelf": "ops", "sources": ["b.txt"]}]},
    ).json()


def test_eval_rerank_needs_the_model(client):
    eval_set = _eval_set(client)
    assert client.get("/api/eval/options").json() == {"reranker_available": False}
    response = client.post("/api/eval/runs", json={"eval_set_id": eval_set["id"], "rerank": True})
    assert response.status_code == 422
    assert "reranker-download" in response.json()["detail"]


def test_eval_run_with_the_reranker(client, runtime, monkeypatch):
    eval_set = _eval_set(client)
    monkeypatch.setattr(eval_service, "model_ready", lambda _dir: True)
    runtime.reranker = PreferWord("GOLDEN")
    run = client.post(
        "/api/eval/runs", json={"eval_set_id": eval_set["id"], "mode": "keyword", "rerank": True}
    ).json()
    client.drain()
    detail = client.get(f"/api/eval/runs/{run['id']}").json()
    assert detail["status"] == "completed"
    assert detail["config"]["rerank"] is True and detail["label"].startswith("keyword+rerank")
    assert runtime.reranker.seen == [2]
    assert detail["results"][0]["first_relevant_rank"] == 1


def test_model_ready_needs_both_files(tmp_path):
    assert not onnx_reranker.model_ready(tmp_path)
    (tmp_path / "onnx").mkdir()
    (tmp_path / onnx_reranker.MODEL_FILE).write_bytes(b"x")
    assert not onnx_reranker.model_ready(tmp_path)
    (tmp_path / "tokenizer.json").write_text("{}")
    assert onnx_reranker.model_ready(tmp_path)


@pytest.mark.skipif(not onnx_reranker.model_ready(LOCAL_MODEL), reason="reranker not downloaded")
def test_real_model_puts_the_answering_passage_first():
    reranker = onnx_reranker.OnnxReranker(LOCAL_MODEL)
    scores = reranker.scores(
        "How many vacation days do I have?",
        [
            "Nitrile gloves must be used when handling resin.",
            "PTO: Years 1-2: 12 days/year. Years 3-5: 16 days/year.",
            "¿Cuántos días de vacaciones? Doce días al año.",
        ],
    )
    assert all(0 <= s <= 1 for s in scores)
    assert scores[1] > scores[0] and scores[2] > scores[0]
