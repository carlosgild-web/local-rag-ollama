"""Quick edit: changed text becomes a new version marked as an edit, with who
and what changed; the original stays as an earlier version."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import AuditLog
from app.main import create_app

CORPUS = Path(__file__).parent / "corpus"
PRICES = (
    "# Wholesale price sheet\n\n"
    "| SKU | Name | Price |\n|---|---|---|\n"
    "| CH-2004 | Crescent Moon & Star | $1.85 |\n"
    "| CH-2011 | Tiny Honeybee | $1.50 |\n"
)


@pytest.fixture
def client(runtime):
    app = create_app(runtime, start_worker=False)
    with TestClient(app) as test_client:
        test_client.drain = app.state.worker.run_until_idle
        yield test_client


def _add(client, name, content, mime="text/markdown"):
    shelf = client.post("/api/collections", json={"name": "operations"}).json()
    response = client.post(
        "/api/documents",
        files=[("files", (name, content, mime))],
        data={"collection_id": str(shelf["id"])},
    )
    assert response.status_code == 202, response.text
    client.drain()
    return client.get("/api/documents").json()[0]


@pytest.fixture
def doc(client):
    return _add(client, "price-sheet.md", PRICES.encode())


def _editable(client, doc):
    url = f"/api/documents/{doc['id']}/versions/{doc['active_version_id']}/text"
    return client.get(url, params={"editable": True}).json()["text"]


def _edit(client, doc_id, text, **extra):
    body = {"text": text, "edited_by": "Carla", **extra}
    return client.post(f"/api/documents/{doc_id}/edit", json=body)


def test_a_markdown_file_is_edited_as_written(client, doc):
    # The editor starts from the file itself, so the table keeps its rows...
    assert _editable(client, doc) == PRICES
    # ...while the searchable text is what the parser extracted.
    url = f"/api/documents/{doc['id']}/versions/{doc['active_version_id']}/text"
    assert client.get(url).json()["text"] != PRICES


def test_an_edit_becomes_the_active_version_with_who_and_what(client, doc, runtime):
    edited = _editable(client, doc).replace("$1.85", "$1.95")
    response = _edit(client, doc["id"], edited, note="Moon charm price for 2027")
    assert response.status_code == 202, response.text
    client.drain()

    after = client.get("/api/documents").json()[0]
    assert (after["filename"], after["version_count"], after["active_version_number"]) == (
        "price-sheet.md",
        2,
        2,
    )
    v2, v1 = client.get(f"/api/documents/{doc['id']}/versions").json()
    assert (v2["origin"], v2["edited_by"], v2["note"], v2["ext"]) == (
        "edit",
        "Carla",
        "Moon charm price for 2027",
        ".md",
    )
    assert v2["is_active"] and v2["chunk_count"] > 0
    assert (v1["origin"], v1["edited_by"]) == ("upload", None)
    text = client.get(f"/api/documents/{doc['id']}/versions/{v2['id']}/text").json()["text"]
    assert "$1.95" in text and "$1.85" not in text
    diff = client.get(
        f"/api/documents/{doc['id']}/diff", params={"a": v1["id"], "b": v2["id"]}
    ).json()
    assert any(line.startswith("+") and "$1.95" in line for line in diff["diff"])
    with runtime.session_factory() as db:
        details = (
            db.execute(select(AuditLog.detail).where(AuditLog.action == "edit")).scalars().all()
        )
    assert details == ["version 2 edited by Carla: Moon charm price for 2027"]


def test_a_word_file_is_edited_as_its_text_and_saved_as_a_text_file(client):
    doc = _add(
        client,
        "configuracion-red-hogar.docx",
        (CORPUS / "configuracion-red-hogar.docx").read_bytes(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    text = _editable(client, doc)
    assert text.strip()
    assert _edit(client, doc["id"], text + "\n\nNota: revisado en 2027.").status_code == 202
    client.drain()
    v2, v1 = client.get(f"/api/documents/{doc['id']}/versions").json()
    assert (v1["ext"], v2["ext"], v2["origin"]) == (".docx", ".txt", "edit")
    # The original Word file is still the first version's original.
    assert client.get(f"/api/documents/{doc['id']}/versions/{v1['id']}/text").status_code == 200


def test_restoring_the_original_after_an_edit(client, doc):
    _edit(client, doc["id"], _editable(client, doc).replace("$1.50", "$1.60"))
    client.drain()
    v2, v1 = client.get(f"/api/documents/{doc['id']}/versions").json()
    client.post(f"/api/documents/{doc['id']}/rollback", json={"version_id": v1["id"]})
    assert client.get("/api/documents").json()[0]["active_version_number"] == 1


def test_unchanged_text_is_refused(client, doc):
    response = _edit(client, doc["id"], _editable(client, doc) + "\n")
    assert response.status_code == 409
    assert "nothing changed" in response.json()["detail"]


def test_text_identical_to_an_earlier_edit_points_to_that_version(client, doc):
    first_edit = _editable(client, doc).replace("$1.85", "$1.95")
    _edit(client, doc["id"], first_edit)
    client.drain()
    _edit(client, doc["id"], first_edit.replace("$1.95", "$2.05"))
    client.drain()
    response = _edit(client, doc["id"], first_edit)
    assert response.status_code == 409
    assert "already version 2" in response.json()["detail"]


def test_a_document_in_the_trash_cant_be_edited(client, doc):
    client.delete(f"/api/documents/{doc['id']}")
    assert _edit(client, doc["id"], "anything new").status_code == 404


def test_the_editor_name_is_required(client, doc):
    response = client.post(
        f"/api/documents/{doc['id']}/edit", json={"text": "new", "edited_by": ""}
    )
    assert response.status_code == 422
