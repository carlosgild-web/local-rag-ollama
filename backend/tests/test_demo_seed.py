"""Loading the demo company from the console: POST /api/demo/seed queues a job."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import AuditLog
from app.main import create_app
from app.versioning import demo


@pytest.fixture
def demo_root(tmp_path, monkeypatch):
    """A tiny demo corpus: two shelves, three files."""
    root = tmp_path / "demo"
    (root / "hr").mkdir(parents=True)
    (root / "ops").mkdir()
    (root / "hr" / "vacation.txt").write_text("Sixteen vacation days in year three.")
    (root / "hr" / "holidays.txt").write_text("The workshop closes from December 24 to January 1.")
    (root / "ops" / "kiln.txt").write_text("Safety glasses at every kiln station.")
    monkeypatch.setattr(demo, "DEMO_DIR", root)
    return root


@pytest.fixture
def client(runtime):
    app = create_app(runtime, start_worker=False)
    with TestClient(app) as test_client:
        test_client.drain = app.state.worker.run_until_idle
        yield test_client


def test_status_offers_the_demo_on_an_empty_library(client, demo_root):
    body = client.get("/api/demo").json()
    assert body == {"available": True, "documents": 0, "job": None}


def test_seed_runs_as_a_job_and_fills_the_library(client, demo_root, runtime):
    response = client.post("/api/demo/seed")
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["job_type"] == "seed_demo"
    assert job["status"] == "pending"
    assert job["subject"].startswith("the demo company")

    client.drain()

    body = client.get("/api/demo").json()
    assert body["documents"] == 3
    assert body["job"]["status"] == "completed"
    assert body["job"]["result"] == {"ingested": 3, "skipped": 0}
    with runtime.session_factory() as db:
        actions = db.execute(select(AuditLog.action)).scalars().all()
    assert "demo_seed" in actions


def test_a_second_request_while_one_is_queued_is_refused(client, demo_root):
    assert client.post("/api/demo/seed").status_code == 202
    assert client.post("/api/demo/seed").status_code == 409


def test_loading_again_skips_every_file(client, demo_root):
    client.post("/api/demo/seed")
    client.drain()
    client.post("/api/demo/seed")
    client.drain()
    job = client.get("/api/demo").json()["job"]
    assert job["result"] == {"ingested": 0, "skipped": 3}
    assert client.get("/api/demo").json()["documents"] == 3


def test_missing_demo_folder_is_a_404(client, tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "DEMO_DIR", tmp_path / "not-there")
    assert client.get("/api/demo").json()["available"] is False
    assert client.post("/api/demo/seed").status_code == 404


def test_seeding_reports_progress_between_files(runtime, demo_root):
    fractions: list[float] = []
    with runtime.session_factory() as db:
        demo.seed_demo(
            db,
            settings=runtime.settings,
            embedding_client_for=runtime.embedding_client_for,
            vector_store=runtime.vector_store,
            root=demo_root,
            progress=fractions.append,
        )
    assert fractions == pytest.approx([1 / 3, 2 / 3, 1.0])


# --- Browsing the original demo documents --------------------------------------


@pytest.fixture
def demo_mixed(tmp_path, monkeypatch):
    """A demo corpus with each kind of file the listing has to describe."""
    root = tmp_path / "demo-mixed"
    (root / "hr").mkdir(parents=True)
    (root / "ops").mkdir()
    (root / "hr" / "holidays.pdf").write_bytes(b"%PDF-1.4 fake pdf for the test")
    (root / "hr" / "policy.docx").write_bytes(b"PK fake docx")
    (root / "ops" / "notes.md").write_text("# Kiln\nSafety glasses on.", encoding="utf-8")
    (root / "ops" / "ignored.exe").write_bytes(b"not a document")
    (root / "secret.txt").write_text("outside any shelf")
    monkeypatch.setattr(demo, "DEMO_DIR", root)
    return root


def test_demo_files_are_listed_by_shelf(client, demo_mixed):
    files = client.get("/api/demo/files").json()
    assert [(f["shelf"], f["name"], f["type"], f["opens_in_browser"]) for f in files] == [
        ("hr", "holidays.pdf", "pdf", True),
        ("hr", "policy.docx", "docx", False),
        ("ops", "notes.md", "md", True),
    ]
    assert files[0]["size"] == len(b"%PDF-1.4 fake pdf for the test")


def test_a_pdf_opens_in_the_browser_and_a_word_file_downloads(client, demo_mixed):
    pdf = client.get("/api/demo/files/hr/holidays.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["content-disposition"].startswith("inline")
    assert pdf.content == b"%PDF-1.4 fake pdf for the test"

    docx = client.get("/api/demo/files/hr/policy.docx")
    assert docx.headers["content-disposition"].startswith("attachment")

    md = client.get("/api/demo/files/ops/notes.md")
    assert md.headers["content-type"].startswith("text/plain")
    assert md.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(
    "path",
    [
        "/api/demo/files/hr/missing.pdf",
        "/api/demo/files/ops/ignored.exe",
        "/api/demo/files/hr/..%2Fsecret.txt",
        "/api/demo/files/..%2F..%2Fdemo-mixed/secret.txt",
        "/api/demo/files/%2E%2E/secret.txt",
    ],
)
def test_only_listed_demo_files_are_served(client, demo_mixed, path):
    assert client.get(path).status_code == 404


def test_an_uploaded_document_can_be_opened_as_uploaded(client, runtime):
    collection = client.post("/api/collections", json={"name": "notes"}).json()
    response = client.post(
        "/api/documents",
        files=[("files", ("kiln.txt", b"Safety glasses at every kiln station.", "text/plain"))],
        data={"collection_id": str(collection["id"])},
    )
    assert response.status_code == 202, response.text
    client.drain()
    document = client.get("/api/documents").json()[0]

    original = client.get(f"/api/documents/{document['id']}/original")
    assert original.status_code == 200
    assert original.content == b"Safety glasses at every kiln station."
    assert original.headers["content-disposition"].startswith("inline")

    assert client.delete(f"/api/documents/{document['id']}").status_code == 204
    assert client.get(f"/api/documents/{document['id']}/original").status_code == 404
    assert client.get("/api/documents/9999/original").status_code == 404
