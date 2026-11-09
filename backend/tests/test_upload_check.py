"""Review before processing (POST /api/documents/check): it predicts what an
upload would do with the same rules ingestion uses, without writing."""

import hashlib

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(runtime):
    app = create_app(runtime, start_worker=False)
    with TestClient(app) as test_client:
        test_client.drain = app.state.worker.run_until_idle
        yield test_client


def _upload(client, name: str, content: bytes, collection_id: int | None = None) -> None:
    data = {"collection_id": str(collection_id)} if collection_id else {}
    response = client.post(
        "/api/documents", files=[("files", (name, content, "text/plain"))], data=data
    )
    assert response.status_code == 202, response.text
    client.drain()


def _candidate(name: str, content: bytes) -> dict:
    return {"name": name, "sha256": hashlib.sha256(content).hexdigest(), "size": len(content)}


def _check(client, files: list[dict], collection_id: int | None = None) -> dict[str, dict]:
    response = client.post(
        "/api/documents/check", json={"collection_id": collection_id, "files": files}
    )
    assert response.status_code == 200, response.text
    return {r["name"]: r for r in response.json()}


def test_upload_rules_name_the_accepted_types_and_size(client):
    rules = client.get("/api/documents/upload-rules").json()
    assert rules == {"extensions": [".docx", ".md", ".pdf", ".txt"], "max_upload_mb": 100}


def test_each_file_gets_the_status_ingestion_would_give_it(client):
    _upload(client, "policy.txt", b"version one")
    _upload(client, "old.txt", b"to be deleted")
    [policy, old] = sorted(client.get("/api/documents").json(), key=lambda d: d["filename"])[::-1]
    client.delete(f"/api/documents/{old['id']}")
    shelf = client.get("/api/collections").json()[0]["id"]

    results = _check(
        client,
        [
            _candidate("brand-new.md", b"fresh"),
            _candidate("policy.txt", b"version two"),  # same name, new content
            _candidate("copy-of-policy.txt", b"version one"),  # same content, other name
            _candidate("old.txt", b"something else"),  # name of a trashed document
            _candidate("photo.png", b"\x89PNG"),
            _candidate("blank.txt", b""),
        ],
        collection_id=shelf,
    )

    assert results["brand-new.md"]["status"] == "new"
    new_version = results["policy.txt"]
    assert new_version["status"] == "new_version"
    assert (new_version["existing_version"], new_version["next_version"]) == (1, 2)
    assert new_version["document_id"] == policy["id"]
    duplicate = results["copy-of-policy.txt"]
    assert duplicate["status"] == "duplicate" and duplicate["existing_filename"] == "policy.txt"
    assert "as 'policy.txt'" in duplicate["message"] and "skipped" in duplicate["message"]
    assert results["old.txt"]["status"] == "name_in_trash"
    assert results["photo.png"]["status"] == "unsupported"
    assert results["blank.txt"]["status"] == "empty"


def test_duplicates_are_found_on_any_shelf_and_checking_writes_nothing(client):
    _upload(client, "faq.txt", b"questions and answers")
    hr = client.post("/api/collections", json={"name": "hr"}).json()["id"]
    jobs_before = client.get("/api/jobs").json()

    results = _check(client, [_candidate("faq.txt", b"questions and answers")], collection_id=hr)

    assert results["faq.txt"]["status"] == "duplicate"
    assert results["faq.txt"]["existing_shelf"] == "default"
    assert client.get("/api/jobs").json() == jobs_before
    assert len(client.get("/api/documents").json()) == 1


def test_too_large_and_retired_shelf_are_refused(client, runtime):
    big = {"name": "huge.pdf", "sha256": "0" * 64, "size": 101 * 1024 * 1024}
    assert _check(client, [big])["huge.pdf"]["status"] == "too_large"

    _upload(client, "a.txt", b"alpha")
    [shelf] = client.get("/api/collections").json()
    client.post(f"/api/collections/{shelf['id']}/reindex", json={"chunk_size_tokens": 300})
    client.drain()
    retired = client.post("/api/documents/check", json={"collection_id": shelf["id"], "files": []})
    assert retired.status_code == 409


def test_a_duplicate_in_the_trash_points_to_restore(client):
    _upload(client, "notes.txt", b"kept in the trash")
    [doc] = client.get("/api/documents").json()
    client.delete(f"/api/documents/{doc['id']}")

    result = _check(client, [_candidate("notes.txt", b"kept in the trash")])["notes.txt"]

    assert result["status"] == "duplicate"
    assert "It's in the trash" in result["message"] and "Restore" in result["message"]
