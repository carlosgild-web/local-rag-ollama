"""The employee portal backend (decision 0010): Luna searches every shelf
that is visible in the portal, its chats are kept apart from the console's,
and the demo corpus loads through the normal ingest service."""

import json
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from app.db.migrate import _config, upgrade_to_head
from app.db.models import AuditLog
from app.db.session import make_engine
from app.main import create_app
from app.retrieval.prompt import SYSTEM_INSTRUCTIONS, with_answer_language
from app.versioning import service
from app.versioning.demo import seed_demo


@pytest.fixture
def client(runtime):
    app = create_app(runtime, start_worker=False)
    with TestClient(app) as test_client:
        test_client.drain = app.state.worker.run_until_idle
        yield test_client


def _upload(client, filename, content, collection_id):
    response = client.post(
        "/api/documents",
        files=[("files", (filename, content, "text/plain"))],
        data={"collection_id": str(collection_id)},
    )
    assert response.status_code == 202, response.text
    client.drain()


def _events(response) -> list[tuple[str, object]]:
    events = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def _two_shelves(client) -> dict[str, int]:
    """'hr' holds vacation rules, 'ops' kiln safety: one fact per shelf."""
    hr = client.post("/api/collections", json={"name": "hr"}).json()["id"]
    ops = client.post("/api/collections", json={"name": "ops", "embedding_model": "other"})
    ops = ops.json()["id"]
    _upload(client, "vacation.txt", b"Employees get sixteen vacation days in year three.", hr)
    _upload(client, "kiln.txt", b"Safety glasses are required at every kiln station.", ops)
    return {"hr": hr, "ops": ops}


def _portal_ask(client, question, **extra):
    response = client.post("/api/chat", json={"question": question, "channel": "intranet", **extra})
    assert response.status_code == 200, response.text
    return _events(response)


def _source_files(events) -> set[str]:
    return {s["filename"] for s in next(data for name, data in events if name == "sources")}


def test_portal_searches_every_shelf_with_its_own_model(client):
    _two_shelves(client)  # the shelves use different embedding models
    events = _portal_ask(client, "vacation days and kiln safety glasses")
    assert _source_files(events) == {"vacation.txt", "kiln.txt"}


def test_shelves_sharing_a_model_are_ranked_together(runtime, monkeypatch):
    """Same-model shelves give ONE vector list ordered by similarity, and FTS
    runs once; only lists that can't be compared are fused by rank. Fusing
    per shelf would give a one-document shelf a top slot for every question."""
    from app.retrieval import retrieve as retrieve_module

    seen: list[list[list[int]]] = []
    real_fuse = retrieve_module.fuse_rrf_scored
    monkeypatch.setattr(
        retrieve_module,
        "fuse_rrf_scored",
        lambda lists, **kw: seen.append(lists) or real_fuse(lists, **kw),
    )
    question = "Employees get sixteen vacation days in year three."

    def shelf(db, name, model, files):
        collection = service.create_collection(
            db, runtime.vector_store, name=name, embedding_model=model
        )
        for filename, body in files.items():
            path = runtime.settings.data_dir / filename
            path.write_text(body)
            service.ingest_document(
                db,
                collection=collection,
                source_path=path,
                settings=runtime.settings,
                embedding_client=runtime.embedding_client_for(model),
                vector_store=runtime.vector_store,
            )
        return collection

    with runtime.session_factory() as db:
        hr = shelf(db, "hr", "m1", {"vacation.txt": question, "sick.txt": "Six sick days."})
        notes = shelf(db, "notes", "m1", {"q3.txt": "Revenue grew in Q3."})
        other = shelf(db, "other", "m2", {"kiln.txt": "Glasses at the kiln."})

        def run(shelves):
            seen.clear()
            return retrieve_module.retrieve_many(
                db,
                question,
                collections=shelves,
                settings=runtime.settings,
                embedding_client_for=runtime.embedding_client_for,
                vector_store=runtime.vector_store,
            )

        results = run([hr, notes])
        [lists] = seen
        assert len(lists) == 2  # one vector list for model m1, one FTS list
        assert results[0].filename == "vacation.txt"  # exact match, top of both lists

        run([hr, notes, other])
        assert len(seen[0]) == 3  # m1 vectors, m2 vectors, FTS


def test_hidden_shelf_is_not_searched_and_the_toggle_is_audited(client):
    shelves = _two_shelves(client)
    patched = client.patch(f"/api/collections/{shelves['ops']}", json={"portal_visible": False})
    assert patched.status_code == 200
    assert patched.json()["portal_visible"] is False
    assert patched.json()["document_count"] == 1

    events = _portal_ask(client, "vacation days and kiln safety glasses")
    assert _source_files(events) == {"vacation.txt"}

    audit = client.get("/api/audit").json()
    assert any(entry["action"] == "collection_portal_visibility" for entry in audit)


def test_no_visible_shelf_answers_not_found(client, runtime):
    shelves = _two_shelves(client)
    for shelf_id in shelves.values():
        client.patch(f"/api/collections/{shelf_id}", json={"portal_visible": False})
    events = _portal_ask(client, "vacation days?")
    done = next(data for name, data in events if name == "done")
    assert done["not_found"] is True
    assert runtime.fake_llm.calls == []


def test_portal_chats_are_kept_apart_from_the_console(client):
    shelves = _two_shelves(client)
    events = _portal_ask(client, "vacation days?")
    portal_session = next(data for name, data in events if name == "session")["session_id"]
    client.post("/api/chat", json={"question": "kiln?", "collection_id": shelves["ops"]})

    admin_list = client.get("/api/sessions").json()
    portal_list = client.get("/api/sessions", params={"channel": "intranet"}).json()
    assert [s["id"] for s in portal_list] == [portal_session]
    assert portal_session not in [s["id"] for s in admin_list]
    assert len(admin_list) == 1

    session = client.get(f"/api/sessions/{portal_session}").json()
    assert session["channel"] == "intranet"
    assert session["collection_id"] is None

    # A follow-up stays in the portal, even without saying so again.
    follow_up = client.post(
        "/api/chat", json={"question": "and kiln glasses?", "session_id": portal_session}
    )
    assert _source_files(_events(follow_up)) >= {"kiln.txt"}


def test_console_all_shelves_searches_every_active_shelf(client):
    """'All shelves' in the console: hidden-from-portal shelves too, saved
    without a shelf so follow-ups keep it, until a shelf is chosen again."""
    shelves = _two_shelves(client)
    client.patch(f"/api/collections/{shelves['ops']}", json={"portal_visible": False})

    def ask(question, **extra):
        response = client.post("/api/chat", json={"question": question, **extra})
        assert response.status_code == 200, response.text
        return _events(response)

    events = ask("vacation days and kiln safety glasses", all_shelves=True)
    assert _source_files(events) == {"vacation.txt", "kiln.txt"}
    session_id = next(data for name, data in events if name == "session")["session_id"]
    session = client.get(f"/api/sessions/{session_id}").json()
    assert session["channel"] == "admin" and session["collection_id"] is None

    follow_up = ask("and kiln glasses?", session_id=session_id)
    assert "kiln.txt" in _source_files(follow_up)

    narrowed = ask("vacation days?", session_id=session_id, collection_id=shelves["hr"])
    assert _source_files(narrowed) == {"vacation.txt"}
    assert client.get(f"/api/sessions/{session_id}").json()["collection_id"] == shelves["hr"]


def test_answer_language_adds_one_rule_to_the_prompt(client, runtime):
    _two_shelves(client)
    _portal_ask(client, "vacation days?", answer_language="es")
    [prompt] = runtime.fake_llm.calls
    assert "5. Write the answer in Spanish." in prompt


def test_with_answer_language_keeps_the_rules():
    assert with_answer_language(None, None) is None
    assert with_answer_language("CUSTOM", None) == "CUSTOM"
    english = with_answer_language(None, "en")
    assert english.startswith(SYSTEM_INSTRUCTIONS)
    assert english.endswith("5. Write the answer in English.")
    # A profile's own rules keep their numbers; unnumbered ones get none.
    assert with_answer_language("1. A\n2. B\n3. C", "es").endswith(
        "\n4. Write the answer in Spanish."
    )
    assert with_answer_language("Be brief.", "en") == "Be brief.\nWrite the answer in English."


def test_swap_keeps_the_portal_setting(runtime):
    with runtime.session_factory() as db:
        source = service.create_collection(
            db, runtime.vector_store, name="hr", embedding_model="m1"
        )
        service.set_portal_visible(db, source.id, False)
        target = service.start_collection_rebuild(
            db,
            runtime.vector_store,
            source.id,
            embedding_model="m2",
            chunk_size_tokens=600,
            chunk_overlap_pct=0.12,
        )
        assert target.portal_visible is True  # until the swap
        service.swap_collection(db, source.id, target.id)
        db.refresh(target)
        assert target.is_active and target.portal_visible is False
        assert service.portal_collections(db) == []


def test_seed_demo_loads_one_shelf_per_folder_and_is_idempotent(runtime, tmp_path):
    root = tmp_path / "demo"
    (root / "hr").mkdir(parents=True)
    (root / "ops").mkdir()
    (root / "hr" / "vacation.txt").write_text("Sixteen vacation days in year three.")
    (root / "ops" / "kiln.txt").write_text("Safety glasses at every kiln station.")
    (root / "notes.txt").write_text("Loose files at the top level are not part of any shelf.")

    def seed():
        with runtime.session_factory() as db:
            return seed_demo(
                db,
                settings=runtime.settings,
                embedding_client_for=runtime.embedding_client_for,
                vector_store=runtime.vector_store,
                root=root,
            )

    first = seed()
    assert [(item.shelf, item.status) for item in first] == [
        ("hr", "ingested"),
        ("ops", "ingested"),
    ]
    assert [item.status for item in seed()] == ["skipped_duplicate", "skipped_duplicate"]

    with runtime.session_factory() as db:
        names = sorted(c.name for c in service.portal_collections(db))
        creates = db.execute(select(AuditLog).where(AuditLog.action == "collection_create")).all()
    assert names == ["hr", "ops"]
    assert len(creates) == 2


def test_seed_demo_ships_the_fictional_corpus():
    root = Path(__file__).resolve().parents[1] / "demo" / "hilda-luna"
    shelves = {p.name: len(list(p.iterdir())) for p in root.iterdir() if p.is_dir()}
    assert shelves == {"hr": 4, "operations": 5, "customer-support": 1, "meetings": 1}


def test_migration_0005_upgrades_and_downgrades(tmp_path):
    db_path = tmp_path / "m.db"
    upgrade_to_head(db_path)

    def columns(table):
        engine = make_engine(db_path)
        try:
            return {c["name"] for c in inspect(engine).get_columns(table)}
        finally:
            engine.dispose()

    assert "portal_visible" in columns("collections")
    assert "channel" in columns("chat_sessions")

    config = _config()
    config.attributes["db_path"] = str(db_path)
    config.attributes["configure_logging"] = False
    command.downgrade(config, "0004_session_collection")
    assert "portal_visible" not in columns("collections")
    assert "channel" not in columns("chat_sessions")
