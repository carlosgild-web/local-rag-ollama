"""The 30-day trash empties itself, and "Delete permanently" works from the
trash only (invariant 3, decision 0018)."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.db.models import Document, IngestJob
from app.main import create_app


def _client(runtime):
    app = create_app(runtime, start_worker=False)
    client = TestClient(app)
    client.__enter__()  # runs the lifespan, which may queue start-up jobs
    client.drain = app.state.worker.run_until_idle
    return client


@pytest.fixture
def client(runtime):
    test_client = _client(runtime)
    yield test_client
    test_client.__exit__(None, None, None)


def _upload(client, filename: str, content: bytes) -> int:
    response = client.post("/api/documents", files=[("files", (filename, content, "text/plain"))])
    assert response.status_code == 202, response.text
    client.drain()
    [doc] = [d for d in client.get("/api/documents").json() if d["filename"] == filename]
    return doc["id"]


def _trash(client, runtime, document_id: int, days_ago: int) -> None:
    assert client.delete(f"/api/documents/{document_id}").status_code == 204
    with runtime.session_factory() as db:
        db.get(Document, document_id).trashed_at = dt.datetime.now(dt.UTC) - dt.timedelta(
            days=days_ago
        )
        db.commit()


def _purge_jobs(runtime) -> list[IngestJob]:
    with runtime.session_factory() as db:
        return list(db.query(IngestJob).filter(IngestJob.job_type == "purge_trash"))


def _purge_audit(client) -> list[dict]:
    return client.get("/api/audit", params={"action": "purge"}).json()


def test_app_start_purges_only_expired_trash(client, runtime):
    old = _upload(client, "old.txt", b"Kiln glasses are kept in drawer two.")
    recent = _upload(client, "recent.txt", b"The loading dock opens at seven.")
    _trash(client, runtime, old, days_ago=31)
    _trash(client, runtime, recent, days_ago=3)
    client.__exit__(None, None, None)

    restarted = _client(runtime)
    try:
        assert len(_purge_jobs(runtime)) == 1
        restarted.drain()
        with runtime.session_factory() as db:
            assert db.get(Document, old) is None
            assert db.get(Document, recent) is not None, "3 days in the trash: kept"
        [entry] = _purge_audit(restarted)
        assert entry["entity_id"] == old and entry["detail"].startswith("old.txt (")
    finally:
        restarted.__exit__(None, None, None)
    client.__enter__()  # the fixture closes it again


def test_app_start_queues_nothing_when_nothing_expired(client, runtime):
    _trash(client, runtime, _upload(client, "recent.txt", b"Fresh in the trash."), days_ago=1)
    client.__exit__(None, None, None)
    _client(runtime).__exit__(None, None, None)
    assert _purge_jobs(runtime) == []
    client.__enter__()


def test_delete_permanently_only_from_the_trash(client, runtime):
    document_id = _upload(client, "notes.txt", b"Glaze batches are logged by the hour.")

    live = client.post(f"/api/documents/{document_id}/purge")
    assert live.status_code == 409, "a live document goes through the trash first"

    client.delete(f"/api/documents/{document_id}")
    queued = client.post(f"/api/documents/{document_id}/purge")
    assert queued.status_code == 202
    client.drain()

    assert client.get(f"/api/documents/{document_id}/versions").status_code == 404
    collections = client.get("/api/collections").json()
    assert all(c["document_count"] == 0 for c in collections)
    assert runtime.vector_store.count(collections[0]["chroma_collection"]) == 0
    [entry] = _purge_audit(client)
    assert entry["detail"].startswith("notes.txt (deleted permanently)")

    [job] = [j for j in client.get("/api/jobs").json() if j["job_type"] == "purge_document"]
    assert job["status"] == "completed" and job["subject"] == "notes.txt"


def test_delete_permanently_unknown_document(client):
    assert client.post("/api/documents/999/purge").status_code == 404
