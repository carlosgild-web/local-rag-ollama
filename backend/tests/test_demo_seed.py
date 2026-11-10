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
