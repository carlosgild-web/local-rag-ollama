"""Profiles: version history, compare and restore (PLAN.md Phase 6)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.retrieval.prompt import SYSTEM_INSTRUCTIONS


@pytest.fixture
def client(runtime):
    app = create_app(runtime, start_worker=False)
    with TestClient(app) as test_client:
        yield test_client


def _save(client, **fields):
    response = client.post("/api/profiles", json=fields)
    assert response.status_code == 201, response.text
    return response.json()


def _versions(client, profile_id):
    return client.get(f"/api/profiles/{profile_id}/versions").json()


def test_compare_lists_changed_fields_and_diffs_the_prompt(client):
    [v1] = client.get("/api/profiles").json()
    v2 = _save(client, retrieval_top_k=8, system_prompt=f"{SYSTEM_INSTRUCTIONS}\nBe brief.")

    body = client.get("/api/profiles/compare", params={"a": v1["id"], "b": v2["id"]}).json()
    assert body["a"]["version"] == 1 and body["b"]["version"] == 2
    assert {c["field"]: (c["a"], c["b"]) for c in body["changes"]} == {
        "retrieval_top_k": (5, 8),
        "system_prompt": (SYSTEM_INSTRUCTIONS, f"{SYSTEM_INSTRUCTIONS}\nBe brief."),
    }
    assert "+Be brief." in body["prompt_diff"]

    same = client.get("/api/profiles/compare", params={"a": v2["id"], "b": v2["id"]}).json()
    assert same["changes"] == [] and same["prompt_diff"] == []


def test_compare_refuses_two_different_profiles_and_unknown_ids(client):
    [default] = client.get("/api/profiles").json()
    other = _save(client, name="experiment", retrieval_top_k=3)
    mixed = client.get("/api/profiles/compare", params={"a": default["id"], "b": other["id"]})
    assert mixed.status_code == 422
    missing = client.get("/api/profiles/compare", params={"a": default["id"], "b": 999})
    assert missing.status_code == 404


def test_restore_saves_the_old_values_as_a_new_version(client):
    [v1] = client.get("/api/profiles").json()
    _save(client, retrieval_top_k=8, temperature=0.3)

    response = client.post(f"/api/profiles/{v1['id']}/restore")
    assert response.status_code == 201
    v3 = response.json()
    assert v3["version"] == 3 and v3["is_active"]
    assert v3["retrieval_top_k"] == v1["retrieval_top_k"] and v3["temperature"] == v1["temperature"]

    versions = _versions(client, v3["id"])
    assert [v["version"] for v in versions] == [3, 2, 1], "history is kept, never rewritten"
    assert [v["is_active"] for v in versions] == [True, False, False]

    audit = client.get("/api/audit", params={"action": "settings_change"}).json()
    assert "restored from v1" in audit[0]["detail"]


def test_restoring_what_is_already_active_is_refused(client):
    [v1] = client.get("/api/profiles").json()
    assert client.post(f"/api/profiles/{v1['id']}/restore").status_code == 409
    assert client.post("/api/profiles/999/restore").status_code == 404


def test_versions_count_the_answers_and_runs_that_used_them(client, runtime):
    from app.db.models import EvalRun, EvalSet
    from app.versioning import history

    [v1] = client.get("/api/profiles").json()
    v2 = _save(client, retrieval_top_k=8)
    with runtime.session_factory() as db:
        session = history.create_session(db, "q")
        for profile_id in (v1["id"], v2["id"], v2["id"]):
            history.add_message(db, session.id, "assistant", "a", rag_profile_id=profile_id)
        eval_set = EvalSet(name="s")
        db.add(eval_set)
        db.flush()
        db.add(EvalRun(eval_set_id=eval_set.id, rag_profile_id=v1["id"], config={}))
        db.commit()

    versions = {v["version"]: v for v in _versions(client, v2["id"])}
    assert (versions[2]["answer_count"], versions[2]["eval_run_count"]) == (2, 0)
    assert (versions[1]["answer_count"], versions[1]["eval_run_count"]) == (1, 1)
