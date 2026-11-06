"""End-to-end API tests against a fake Runtime (no Ollama, no Chroma)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.retrieval.prompt import NOT_FOUND_PHRASE

CORPUS = Path(__file__).parent / "corpus"


@pytest.fixture
def client(runtime):
    app = create_app(runtime, start_worker=False)
    with TestClient(app) as test_client:
        test_client.drain = app.state.worker.run_until_idle
        yield test_client


def _upload(client, filename, content, **form):
    response = client.post(
        "/api/documents", files=[("files", (filename, content, "text/plain"))], data=form
    )
    assert response.status_code == 202, response.text
    client.drain()
    return response.json()["jobs"][0]["job_id"]


def _job(client, job_id):
    return next(j for j in client.get("/api/jobs").json() if j["id"] == job_id)


def _events(response) -> list[tuple[str, object]]:
    events = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_openapi_lists_every_phase3_route(client):
    paths = client.get("/openapi.json").json()["paths"]
    expected = {
        ("post", "/api/documents"),
        ("get", "/api/documents"),
        ("delete", "/api/documents/{document_id}"),
        ("post", "/api/documents/{document_id}/reindex"),
        ("get", "/api/documents/{document_id}/versions"),
        ("get", "/api/documents/{document_id}/diff"),
        ("post", "/api/documents/{document_id}/rollback"),
        ("get", "/api/collections"),
        ("post", "/api/collections"),
        ("post", "/api/collections/{collection_id}/reindex"),
        ("post", "/api/chat"),
        ("get", "/api/sessions"),
        ("get", "/api/sessions/{session_id}"),
        ("post", "/api/messages/{message_id}/feedback"),
        ("post", "/api/retrieve"),
        ("get", "/api/jobs"),
        ("post", "/api/jobs/{job_id}/retry"),
        ("post", "/api/jobs/{job_id}/cancel"),
        ("get", "/api/models"),
        ("post", "/api/models/pull"),
        ("delete", "/api/models/{name}"),
        ("get", "/api/profiles"),
        ("post", "/api/profiles"),
        ("get", "/api/profiles/{profile_id}/versions"),
        ("get", "/api/audit"),
        ("get", "/api/health"),
    }
    actual = {(method, path) for path, ops in paths.items() for method in ops}
    assert expected <= actual, expected - actual


def test_upload_version_diff_rollback_delete_flow(client):
    first_job = _upload(
        client, "notes.txt", b"The espresso machine is red.", tags="coffee, kitchen"
    )
    result = _job(client, first_job)["result"]
    assert result["status"] == "ingested"
    document_id = result["document_id"]
    assert "staged_path" not in _job(client, first_job)["payload"]

    # same content again: duplicate
    dup_job = _upload(client, "other-name.txt", b"The espresso machine is red.")
    assert _job(client, dup_job)["result"]["status"] == "skipped_duplicate"

    # same name, new content: new version
    _upload(client, "notes.txt", b"The espresso machine is blue.")

    [document] = client.get("/api/documents").json()
    assert document["id"] == document_id
    assert document["version_count"] == 2
    assert document["active_version_number"] == 2
    assert document["tags"] == ["coffee", "kitchen"]
    assert client.get("/api/documents", params={"tag": "coffee"}).json()
    assert client.get("/api/documents", params={"tag": "cof"}).json() == []

    versions = client.get(f"/api/documents/{document_id}/versions").json()
    v2, v1 = versions
    assert v2["is_active"] and not v1["is_active"]
    assert v1["chunk_count"] > 0

    diff = client.get(
        f"/api/documents/{document_id}/diff", params={"a": v1["id"], "b": v2["id"]}
    ).json()["diff"]
    assert any(line.startswith("-") and "red" in line for line in diff)
    assert any(line.startswith("+") and "blue" in line for line in diff)

    rolled = client.post(f"/api/documents/{document_id}/rollback", json={"version_id": v1["id"]})
    assert rolled.status_code == 200
    assert rolled.json()["version_number"] == 1
    assert client.get("/api/documents").json()[0]["active_version_number"] == 1

    assert client.delete(f"/api/documents/{document_id}").status_code == 204
    assert client.get("/api/documents").json() == []
    assert client.get("/api/documents", params={"trashed": True}).json()[0]["id"] == document_id

    actions = {entry["action"] for entry in client.get("/api/audit").json()}
    assert {"upload", "rollback", "delete"} <= actions


def test_upload_rejects_unsupported_type(client):
    response = client.post(
        "/api/documents", files=[("files", ("tool.exe", b"MZ", "application/octet-stream"))]
    )
    assert response.status_code == 415


def test_diff_rejects_versions_of_another_document(client):
    a = _job(client, _upload(client, "a.txt", b"alpha"))["result"]
    b = _job(client, _upload(client, "b.txt", b"beta"))["result"]
    response = client.get(
        f"/api/documents/{a['document_id']}/diff",
        params={"a": a["version_id"], "b": b["version_id"]},
    )
    assert response.status_code == 404


def test_reindex_document_queues_and_completes(client):
    document_id = _job(client, _upload(client, "a.txt", b"alpha beta"))["result"]["document_id"]
    response = client.post(f"/api/documents/{document_id}/reindex")
    assert response.status_code == 202
    client.drain()
    assert _job(client, response.json()["job_id"])["status"] == "completed"


def test_collections_create_conflict_and_blue_green_reindex(client):
    created = client.post("/api/collections", json={"name": "papers", "embedding_model": "m1"})
    assert created.status_code == 201
    collection_id = created.json()["id"]
    assert client.post("/api/collections", json={"name": "papers"}).status_code == 409

    _upload(client, "paper.txt", b"Telescopes gather light.", collection_id=str(collection_id))

    in_place = client.post(f"/api/collections/{collection_id}/reindex")
    assert in_place.status_code == 202
    assert in_place.json()["mode"] == "in_place"
    client.drain()

    rebuild = client.post(
        f"/api/collections/{collection_id}/reindex", json={"embedding_model": "m2"}
    ).json()
    assert rebuild["mode"] == "blue_green"
    client.drain()
    assert _job(client, rebuild["job_id"])["status"] == "completed"

    active = {c["name"]: c for c in client.get("/api/collections").json()}
    assert active["papers"]["id"] == rebuild["target_collection_id"]
    assert active["papers"]["embedding_model"] == "m2"
    assert active["papers"]["document_count"] == 1
    everything = client.get("/api/collections", params={"include_inactive": True}).json()
    assert any(c["id"] == collection_id and not c["is_active"] for c in everything)

    found = client.post(
        "/api/retrieve", json={"question": "telescopes", "collection_id": active["papers"]["id"]}
    ).json()
    assert found["chunks"]


def test_retrieve_returns_ranked_chunks_with_scores(client):
    _upload(client, "coffee.txt", (CORPUS / "coffee-brewing-methods.txt").read_bytes())
    body = client.post("/api/retrieve", json={"question": "espresso", "top_k": 3}).json()
    assert 0 < len(body["chunks"]) <= 3
    assert [c["rank"] for c in body["chunks"]] == list(range(1, len(body["chunks"]) + 1))
    assert all(c["score"] > 0 and c["filename"] == "coffee.txt" for c in body["chunks"])


def test_chat_streams_and_records_sources_profile_and_feedback(client, runtime):
    _upload(client, "coffee.txt", (CORPUS / "coffee-brewing-methods.txt").read_bytes())
    runtime.fake_llm._responses.append("Espresso is brewed under pressure [1].")

    response = client.post("/api/chat", json={"question": "How is espresso brewed?"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response)

    names = [name for name, _ in events]
    assert names[0] == "session" and names[1] == "sources" and names[-1] == "done"
    sources = events[1][1]
    assert sources and sources[0]["filename"] == "coffee.txt"
    answer = "".join(data["text"] for name, data in events if name == "token")
    assert answer == "Espresso is brewed under pressure [1]."
    done = events[-1][1]
    session_id = events[0][1]["session_id"]

    session = client.get(f"/api/sessions/{session_id}").json()
    user, assistant = session["messages"]
    assert user["role"] == "user" and assistant["role"] == "assistant"
    assert assistant["id"] == done["message_id"]
    assert assistant["content"] == answer
    assert assistant["rag_profile_id"] == done["rag_profile_id"] is not None
    assert [s["chunk_id"] for s in assistant["sources"]] == [s["chunk_id"] for s in sources]

    feedback = client.post(
        f"/api/messages/{assistant['id']}/feedback", json={"thumbs_up": False, "comment": "vague"}
    )
    assert feedback.status_code == 200
    again = client.post(f"/api/messages/{assistant['id']}/feedback", json={"thumbs_up": True})
    assert again.json()["thumbs_up"] is True
    assert client.get(f"/api/sessions/{session_id}").json()["messages"][1]["feedback"]["thumbs_up"]
    assert (
        client.post(f"/api/messages/{user['id']}/feedback", json={"thumbs_up": True}).status_code
        == 409
    )

    # follow-up in the same session
    client.post("/api/chat", json={"question": "And pour-over?", "session_id": session_id})
    [summary] = client.get("/api/sessions").json()
    assert summary["message_count"] == 4


def test_chat_with_empty_knowledge_base_answers_not_found(client, runtime):
    client.post("/api/collections", json={"name": "empty"})
    events = _events(client.post("/api/chat", json={"question": "Anything?"}))
    tokens = [data["text"] for name, data in events if name == "token"]
    assert tokens == [NOT_FOUND_PHRASE]
    assert events[1] == ("sources", [])
    assert events[-1][1]["not_found"] is True
    assert runtime.fake_llm.calls == []


def test_chat_unknown_session_is_404(client):
    assert client.post("/api/chat", json={"question": "x", "session_id": 999}).status_code == 404


def test_jobs_cancel_and_retry_endpoints(client):
    response = client.post("/api/documents", files=[("files", ("a.txt", b"alpha", "text/plain"))])
    job_id = response.json()["jobs"][0]["job_id"]

    cancelled = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancelled.json()["status"] == "cancelled"
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 409
    assert client.get("/api/jobs", params={"status": "cancelled"}).json()[0]["id"] == job_id

    # the staged file is kept until the worker sees the job, so retry still works
    assert client.post(f"/api/jobs/{job_id}/retry").json()["status"] == "pending"
    client.drain()
    assert _job(client, job_id)["status"] == "completed"
    assert client.post(f"/api/jobs/{job_id}/retry").status_code == 409
    assert client.post("/api/jobs/999/retry").status_code == 404


def test_models_list_pull_and_delete(client):
    names = [m["name"] for m in client.get("/api/models").json()]
    assert "llama3.1:latest" in names

    events = _events(client.post("/api/models/pull", json={"name": "qwen2.5:7b"}))
    assert events[0][0] == "progress"
    assert events[-1] == ("done", {"name": "qwen2.5:7b", "status": "success"})

    assert client.delete("/api/models/llama3.1:latest").status_code == 204
    assert client.delete("/api/models/missing:latest").status_code == 404
    actions = {e["action"] for e in client.get("/api/audit").json()}
    assert {"model_pull", "model_delete"} <= actions


def test_profiles_are_versioned_and_keep_the_grounding_rule(client):
    [default] = client.get("/api/profiles").json()
    assert default["name"] == "default" and default["version"] == 1

    saved = client.post("/api/profiles", json={"retrieval_top_k": 8, "temperature": 0.1})
    assert saved.status_code == 201
    assert saved.json()["version"] == 2
    assert saved.json()["chat_model"] == default["chat_model"], "omitted fields carry over"

    versions = client.get(f"/api/profiles/{saved.json()['id']}/versions").json()
    assert [v["version"] for v in versions] == [2, 1]
    assert [v["is_active"] for v in versions] == [True, False]

    bad = client.post("/api/profiles", json={"system_prompt": "Answer anything you like."})
    assert bad.status_code == 422

    audit = client.get("/api/audit", params={"action": "settings_change"}).json()
    assert len(audit) == 2


def test_health_reports_components(client, runtime):
    body = client.get("/api/health").json()
    assert body["sqlite"]["ok"] and body["vector_store"]["ok"] and body["ollama"]["ok"]
    assert body["status"] == "degraded", "worker is not started in tests"
    assert client.get("/health").status_code == 200

    runtime.vector_store.fail_ping = True
    down = client.get("/api/health")
    assert down.status_code == 503
    assert down.json()["status"] == "down"


def test_unknown_ids_are_404(client):
    assert client.delete("/api/documents/42").status_code == 404
    assert client.get("/api/documents/42/versions").status_code == 404
    assert client.get("/api/sessions/42").status_code == 404
    assert client.post("/api/collections/42/reindex").status_code == 404
    assert client.get("/api/profiles/42/versions").status_code == 404


def test_swagger_gets_a_file_picker_and_minimal_examples(runtime):
    schema = create_app(runtime, start_worker=False).openapi()
    components = schema["components"]["schemas"]
    upload = next(v for k, v in components.items() if k.startswith("Body_upload_documents"))
    assert upload["properties"]["files"]["items"]["format"] == "binary"
    # Swagger prefills the example; ids of 0 would 404, so only the question is set.
    assert components["ChatIn"]["examples"] == [{"question": "What does the document say about X?"}]


def test_upload_treats_empty_form_fields_as_unset(runtime):
    with TestClient(create_app(runtime, start_worker=False)) as client:
        response = client.post(
            "/api/documents",
            data={"collection_id": "", "tags": ""},
            files=[("files", ("a.txt", b"alpha", "text/plain"))],
        )
    assert response.status_code == 202, response.text


def test_timestamps_are_marked_utc(runtime):
    with TestClient(create_app(runtime, start_worker=False)) as client:
        client.post("/api/documents", files=[("files", ("a.txt", b"alpha", "text/plain"))])
        [job] = client.get("/api/jobs").json()
    assert job["created_at"].endswith("Z") or job["created_at"].endswith("+00:00")


# --- Which shelf a question searches (end-to-end test 2026-11-06) ----------


def _collection_ids(client):
    return {c["name"]: c["id"] for c in client.get("/api/collections").json()}


def test_questions_never_create_a_collection(client):
    response = client.post("/api/chat", json={"question": "Anything?"})
    assert response.status_code == 409
    assert "no collections yet" in response.json()["detail"]
    assert client.get("/api/collections").json() == []


def test_question_without_a_shelf_needs_a_choice_when_several_exist(client):
    client.post("/api/collections", json={"name": "hr"})
    client.post("/api/collections", json={"name": "sales"})
    response = client.post("/api/chat", json={"question": "Anything?"})
    assert response.status_code == 409
    assert "choose a collection" in response.json()["detail"]
    assert sorted(_collection_ids(client)) == ["hr", "sales"]  # no 'default' appeared


def test_chat_session_remembers_its_shelf_for_follow_ups(client):
    client.post("/api/collections", json={"name": "hr"})
    client.post("/api/collections", json={"name": "sales"})
    ids = _collection_ids(client)
    first = _events(
        client.post("/api/chat", json={"question": "First?", "collection_id": ids["sales"]})
    )
    session_id = first[0][1]["session_id"]

    follow_up = client.post("/api/chat", json={"question": "And?", "session_id": session_id})

    assert follow_up.status_code == 200
    session = client.get(f"/api/sessions/{session_id}").json()
    assert session["collection_id"] == ids["sales"]
    listed = next(s for s in client.get("/api/sessions").json() if s["id"] == session_id)
    assert listed["collection_id"] == ids["sales"]


def test_retired_collection_copy_is_refused_and_sessions_follow_the_rebuild(client):
    _upload(client, "a.txt", b"alpha beta gamma")
    [default] = client.get("/api/collections").json()
    first = _events(
        client.post("/api/chat", json={"question": "alpha?", "collection_id": default["id"]})
    )
    session_id = first[0][1]["session_id"]
    client.post(f"/api/collections/{default['id']}/reindex", json={"chunk_size_tokens": 300})
    client.drain()
    new_id = _collection_ids(client)["default"]
    assert new_id != default["id"]

    retired = client.post("/api/chat", json={"question": "x", "collection_id": default["id"]})
    assert retired.status_code == 409 and "retired copy" in retired.json()["detail"]

    follow_up = client.post("/api/chat", json={"question": "and?", "session_id": session_id})
    assert follow_up.status_code == 200
    assert client.get(f"/api/sessions/{session_id}").json()["collection_id"] == new_id
