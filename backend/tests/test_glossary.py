"""The glossary (decision 0021): the documents' words are written into the question."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import AuditLog
from app.main import create_app
from app.retrieval.glossary import Term, expand_question

TERMS = [
    Term("vacation", "PTO, paid time off"),
    Term("time off", "PTO, paid time off"),
    Term("urgente", "rush"),
    Term("quit", "voluntary resignation"),
]


def test_a_term_gets_its_meaning_right_after_it():
    assert expand_question("How many vacation days do I have?", TERMS) == (
        "How many vacation (PTO, paid time off) days do I have?"
    )


def test_matching_ignores_case_accents_and_plural_endings():
    assert expand_question("VACATIONS?", TERMS) == "VACATIONS (PTO, paid time off)?"
    assert expand_question("¿Pedidos urgentes?", TERMS) == "¿Pedidos urgentes (rush)?"
    assert expand_question("Urgénte", [Term("urgente", "rush")]) == "Urgénte (rush)"


def test_only_whole_words_match():
    assert expand_question("Is it quite late?", TERMS) == "Is it quite late?"


def test_multi_word_terms_and_each_term_once():
    assert expand_question("Can I take time off on vacation, vacation?", TERMS) == (
        "Can I take time off (PTO, paid time off) on vacation (PTO, paid time off), vacation?"
    )


def test_a_meaning_already_in_the_question_is_not_repeated():
    question = "How many PTO, paid time off days are vacation days?"
    assert expand_question(question, TERMS) == question


def test_no_terms_no_change():
    assert expand_question("How many vacation days?", []) == "How many vacation days?"


# --- API, chat and evaluation ----------------------------------------------------------


@pytest.fixture
def client(runtime):
    app = create_app(runtime, start_worker=False)
    with TestClient(app) as test_client:
        test_client.drain = app.state.worker.run_until_idle
        yield test_client


def test_glossary_entries_are_validated_and_audited(client, runtime):
    added = client.post(
        "/api/glossary", json={"term": " vacation ", "means": "PTO,  paid time off"}
    )
    assert added.status_code == 201
    assert added.json()["term"] == "vacation" and added.json()["means"] == "PTO, paid time off"
    assert client.post("/api/glossary", json={"term": "Vacation", "means": "x"}).status_code == 409
    assert client.post("/api/glossary", json={"term": "pto", "means": "PTO"}).status_code == 422

    preview = client.get("/api/glossary/preview", params={"question": "Vacation days?"}).json()
    assert preview["expanded"] == "Vacation (PTO, paid time off) days?"

    assert client.delete(f"/api/glossary/{added.json()['id']}").status_code == 204
    assert client.get("/api/glossary").json() == []
    assert client.delete(f"/api/glossary/{added.json()['id']}").status_code == 404
    with runtime.session_factory() as db:
        actions = [a.action for a in db.execute(select(AuditLog)).scalars()]
    assert actions.count("glossary_add") == 1 and "glossary_delete" in actions


def test_demo_terms_load_once(client):
    first = client.post("/api/glossary/demo").json()
    assert {t["term"] for t in first} >= {"vacation", "vacaciones"}
    assert client.post("/api/glossary/demo").json() == []  # nothing new the second time


def _shelf_with_pto(client):
    shelf = client.post("/api/collections", json={"name": "hr"}).json()["id"]
    client.post(
        "/api/documents",
        files=[("files", ("policy.txt", b"PTO: 12 days per year in years 1-2.", "text/plain"))],
        data={"collection_id": str(shelf)},
    )
    client.drain()
    client.post("/api/glossary", json={"term": "vacation", "means": "PTO, paid time off"})
    return shelf


def test_chat_asks_the_expanded_question_but_keeps_the_original(client, runtime):
    shelf = _shelf_with_pto(client)
    runtime.fake_llm._responses.append("12 days of PTO per year [1].")
    client.post("/api/chat", json={"question": "How many vacation days?", "collection_id": shelf})

    assert "Question: How many vacation (PTO, paid time off) days?" in runtime.fake_llm.calls[-1]
    session = client.get("/api/sessions").json()[0]
    messages = client.get(f"/api/sessions/{session['id']}").json()["messages"]
    assert messages[0]["content"] == "How many vacation days?"


def test_eval_runs_record_the_glossary_and_can_skip_it(client, runtime):
    _shelf_with_pto(client)
    eval_set = client.post(
        "/api/eval/sets/import",
        json={"name": "s", "cases": [{"question": "How many vacation days?", "shelf": "hr",
                                       "sources": ["policy.txt"], "facts": [["12"]]}]},
    ).json()  # fmt: skip

    for use in (True, False):
        run = client.post(
            "/api/eval/runs",
            json={"eval_set_id": eval_set["id"], "answers": True, "glossary": use},
        ).json()
        client.drain()
        config = client.get(f"/api/eval/runs/{run['id']}").json()["config"]
        assert config["use_glossary"] is use
        assert config["glossary"] == (
            [{"term": "vacation", "means": "PTO, paid time off"}] if use else []
        )
    with_glossary, without = runtime.fake_llm.calls[-2:]
    assert "vacation (PTO, paid time off) days" in with_glossary
    assert "PTO, paid time off" not in without.split("Question:")[1]
    assert client.get("/api/eval/runs").json()[0]["label"].endswith("no glossary")
