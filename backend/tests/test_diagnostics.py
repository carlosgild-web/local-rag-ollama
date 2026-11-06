"""The troubleshooter (GET /api/diagnostics): each failure names its cause
and fix, and SIMULATE_FAULTS reproduces every one of them."""

import dataclasses

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.models import IngestJob
from app.main import create_app


def _client(runtime, **settings):
    rt = dataclasses.replace(runtime, settings=runtime.settings.model_copy(update=settings))
    app = create_app(rt, start_worker=False)
    client = TestClient(app)
    client.app_state = app.state
    return client


def _checks(client) -> dict[str, dict]:
    report = client.get("/api/diagnostics").json()
    return {c["id"]: c for c in report["checks"]} | {"_report": report}


def test_everything_ok_on_a_healthy_install(runtime):
    with _client(runtime) as client:
        client.app_state.worker.start()
        checks = _checks(client)
        client.app_state.worker.stop()
    report = checks.pop("_report")
    bad = {
        k: (c["status"], c["detail"])
        for k, c in checks.items()
        if c["status"] not in ("ok", "skip")
    }
    assert bad == {} and report["status"] == "ok" and report["simulated"] == []


@pytest.mark.parametrize(
    ("fault", "check_id", "skipped", "health_status"),
    [
        ("sqlite", "sqlite.open", ["sqlite.integrity", "sqlite.schema", "sqlite.fts"], "down"),
        ("vector_store", "vector.open", [], "down"),
        (
            "ollama_down",
            "ollama.reachable",
            ["ollama.version", "ollama.models", "ollama.memory"],
            "degraded",
        ),
        ("ollama_version", "ollama.version", [], None),
        ("model_missing", "ollama.model.llama3.1", [], None),
        ("worker", "jobs.worker", [], "degraded"),
    ],
)
def test_each_simulated_fault_explains_cause_and_fix(
    runtime, fault, check_id, skipped, health_status
):
    with _client(runtime, simulate_faults=fault) as client:
        checks = _checks(client)
        health = client.get("/api/health")

    report = checks.pop("_report")
    failed = checks[check_id]
    assert failed["status"] == "fail" and report["status"] == "fail"
    assert failed["cause"] and failed["fix"], failed
    assert "simulated" in failed["detail"]
    assert all(checks[s]["status"] == "skip" for s in skipped)
    assert report["simulated"] == [fault]
    assert health.json()["simulated"] == [fault]
    if health_status:
        assert health.json()["status"] == health_status


def test_missing_model_offers_to_download_it(runtime):
    with _client(runtime, chat_model="qwen2.5:3b") as client:
        checks = _checks(client)
    missing = checks["ollama.model.qwen2.5:3b"]
    assert missing["status"] == "fail"
    assert missing["action"] == {
        "kind": "pull_model",
        "label": "Download qwen2.5:3b",
        "target": "qwen2.5:3b",
    }
    assert "ollama pull qwen2.5:3b" in missing["commands"]


def test_chat_model_used_for_embeddings_is_flagged(runtime):
    with _client(runtime) as client:
        client.post("/api/collections", json={"name": "oops", "embedding_model": "llama3.1"})
        checks = _checks(client)
    wrong = checks["ollama.model.llama3.1"]
    assert wrong["status"] == "fail" and "chat model" in wrong["detail"]


def test_search_index_out_of_step_offers_a_reindex(runtime):
    with _client(runtime) as client:
        client.post(
            "/api/documents", files=[("files", ("a.txt", b"alpha beta gamma", "text/plain"))]
        )
        client.app_state.worker.run_until_idle()
        [shelf] = client.get("/api/collections").json()
        runtime.vector_store._collections[shelf["chroma_collection"]].clear()  # vectors lost
        checks = _checks(client)
    out_of_step = checks[f"vector.shelf.{shelf['id']}"]
    assert (
        out_of_step["status"] == "warn"
        and "0 passages in the search index" in out_of_step["detail"]
    )
    assert out_of_step["action"]["kind"] == "reindex_collection"
    assert out_of_step["action"]["target"] == str(shelf["id"])


def test_failed_jobs_and_an_old_schema_are_reported(runtime):
    with runtime.session_factory() as db:
        db.add(IngestJob(job_type="ingest", payload="{}", status="failed", error="boom"))
        db.execute(text("UPDATE alembic_version SET version_num = '0001_old'"))
        db.commit()
    with _client(runtime) as client:
        checks = _checks(client)
    assert checks["jobs.failed"]["status"] == "warn"
    assert checks["jobs.failed"]["action"]["kind"] == "open_queue"
    schema = checks["sqlite.schema"]
    assert schema["status"] == "fail" and "0001_old" in schema["detail"]


def test_unknown_fault_names_are_ignored(runtime):
    with _client(runtime, simulate_faults="nonsense, sqlite") as client:
        assert client.get("/api/diagnostics").json()["simulated"] == ["sqlite"]


def test_support_draft_is_prefilled_from_the_checks(runtime):
    with _client(runtime, simulate_faults="sqlite") as client:
        draft = client.get("/api/support/draft").json()
    env = draft["environment"]
    assert (
        env["computer_name"]
        and env["user_name"]
        and env["configuration_item"].startswith("Local RAG on ")
    )
    assert draft["assignment_group"] == "L2 Application Support"
    # the database is down: the whole app is unusable -> impact 2, urgency 1 -> P2
    assert (draft["impact"], draft["urgency"], draft["priority"]) == (2, 1, "2 - High")
    assert draft["short_description"].startswith("Local RAG: check 'Database opens' is failing")
    assert any(p["title"] == "Database opens" for p in draft["problems"])
    assert draft["simulated_faults"] == ["sqlite"]


def test_support_ticket_is_filed_locally_as_a_numbered_incident(runtime):
    """Submitting is simulated: nothing leaves the machine; the incident a
    real integration would send is saved instead, with an INC number."""
    with runtime.session_factory() as db:
        db.add(IngestJob(job_type="ingest", payload="{}", status="failed", error="boom"))
        db.commit()
    body = {
        "caller_name": "Carlos",
        "contact": "ext. 1234",
        "impact": 1,
        "urgency": 2,
        "short_description": "Chat stopped answering",
        "description": "After the patch from yesterday the system is down.",
        "recent_changes": "Windows patch KB000000 installed yesterday",
    }
    with _client(runtime, simulate_faults="ollama_down") as client:
        first = client.post("/api/support/tickets", json=body)
        second = client.post("/api/support/tickets", json=body)
        audit = client.get("/api/audit", params={"action": "support_ticket"}).json()
        missing = client.post("/api/support/tickets", json={**body, "description": ""})

    assert first.status_code == 201
    ticket = first.json()
    incident = ticket["incident"]
    assert ticket["number"] == "INC0010001" and second.json()["number"] == "INC0010002"
    assert incident["state"] == "New" and incident["simulated"] is True
    assert incident["priority"] == "2 - High"  # impact 1, urgency 2
    assert incident["response_due"] > incident["opened_at"]
    assert incident["description"].startswith("After the patch")
    assert incident["user_details"]["recent_changes"].startswith("Windows patch")
    assert incident["work_notes"]["recent_failed_jobs"][0]["error"] == "boom"
    assert any(p["title"] == "Ollama is reachable" for p in incident["work_notes"]["problems"])
    assert "checks" in incident["attachments"]["diagnostics.json"]

    saved = runtime.settings.support_dir / "INC0010001.json"
    assert saved.exists() and "After the patch" in saved.read_text(encoding="utf-8")
    assert {a["detail"].split()[0] for a in audit} == {"INC0010001", "INC0010002"}
    assert missing.status_code == 422  # "what happened" is required
