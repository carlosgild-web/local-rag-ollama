"""Intake (decision 0009): the app suggests a shelf and tags for every file
before anything is indexed, and only the user's confirmation creates shelves
and queues ingestion."""

import datetime as dt
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.ingest import intake
from app.llm.base import EmbeddingClient
from app.main import create_app

STAFF_WORDS = ("employee", "holiday", "onboarding", "human resources")
BUSINESS_WORDS = ("price", "catalog", "sales", "customer")


class TopicEmbedder(EmbeddingClient):
    """Controlled vectors: one axis for staff words, one for business words,
    plus a small shared component, so similarities are predictable."""

    dimensions = 4

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            low = text.lower()
            staff = sum(low.count(w) for w in STAFF_WORDS)
            business = sum(low.count(w) for w in BUSINESS_WORDS)
            out.append([float(staff), float(business), 0.3, 0.1])
        return out


STAFF_A = b"Employee holiday rules: every employee gets 25 holiday days in 2026."
STAFF_B = b"Onboarding checklist for a new employee: badge, laptop, holiday calendar."
BIZ_A = b"Product catalog with the price of each item for sales in Q4 2026."
BIZ_B = b"Customer questions about sales orders and the price of shipping."


@pytest.fixture
def client(runtime):
    embedder = TopicEmbedder()
    runtime.embedding_client_for = lambda _model: embedder
    app = create_app(runtime, start_worker=False)
    with TestClient(app) as test_client:
        test_client.drain = app.state.worker.run_until_idle
        test_client.runtime = runtime
        yield test_client


def _start(client, files: list[tuple[str, bytes]]) -> str:
    response = client.post(
        "/api/intake",
        files=[("files", (path.split("/")[-1], content, "text/plain")) for path, content in files],
        data={"paths": [path for path, _ in files]},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["files"] == len(files)
    return body["batch_id"]


def _analyze(client, files: list[tuple[str, bytes]]) -> tuple[str, dict]:
    batch_id = _start(client, files)
    client.drain()
    result = client.get(f"/api/intake/{batch_id}").json()
    assert result["state"] == "ready"
    return batch_id, result


def _by_name(result: dict) -> dict[str, dict]:
    return {f["name"]: f for f in result["files"]}


def _confirm(client, batch_id: str, result: dict, new_shelves: dict[str, str], **changes):
    files = [
        {
            "key": f["key"],
            "include": f["include"],
            "shelf": f["shelf"] or "",
            "tags": f["tags"],
            **changes.get(f["name"], {}),
        }
        for f in result["files"]
        if f["shelf"]
    ]
    return client.post(
        f"/api/intake/{batch_id}/confirm", json={"new_shelves": new_shelves, "files": files}
    )


def _upload(client, name: str, content: bytes, collection_id: int) -> None:
    response = client.post(
        "/api/documents",
        files=[("files", (name, content, "text/plain"))],
        data={"collection_id": str(collection_id)},
    )
    assert response.status_code == 202, response.text
    client.drain()


def test_new_files_are_grouped_by_audience_and_nothing_is_indexed_before_confirm(client):
    # One call names every new shelf (business before staff); chatter
    # around the JSON and a name needing a slug are tolerated.
    client.runtime.fake_llm._responses.append(
        'Sure! {"shelves": [{"name": "business-docs", "description": "Sales and customers."},'
        ' {"name": "Employees HR", "description": "For staff."}]}'
    )
    batch_id, result = _analyze(
        client,
        [
            ("Picked/holidays.txt", STAFF_A),
            ("Picked/onboarding.txt", STAFF_B),
            ("Picked/catalog.txt", BIZ_A),
            ("Picked/customers.txt", BIZ_B),
        ],
    )
    files = _by_name(result)
    assert {f["status"] for f in files.values()} == {"new"}
    assert files["holidays.txt"]["shelf"] == files["onboarding.txt"]["shelf"]
    assert files["catalog.txt"]["shelf"] == files["customers.txt"]["shelf"]
    assert files["holidays.txt"]["shelf"] != files["catalog.txt"]["shelf"]
    new = {s["ref"]: s for s in result["shelves"] if not s["existing"]}
    assert {s["name"] for s in new.values()} == {"business-docs", "employees-hr"}
    assert {s["named_by"] for s in new.values()} == {"model"}
    assert "hr" in files["holidays.txt"]["tags"]
    assert "2026" in files["holidays.txt"]["tags"]
    assert "q4-2026" in files["catalog.txt"]["tags"]

    # Analysis wrote nothing to the library.
    assert client.get("/api/documents").json() == []
    assert client.get("/api/collections").json() == []

    staff_ref = files["holidays.txt"]["shelf"]
    business_ref = files["catalog.txt"]["shelf"]
    response = _confirm(
        client,
        batch_id,
        result,
        {staff_ref: "staff", business_ref: "business"},
        **{
            "customers.txt": {"shelf": staff_ref},  # the user moves one file
            "holidays.txt": {"tags": ["hr", "leave"]},  # and edits tags
            "onboarding.txt": {"include": False},  # and leaves one out
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["job_ids"]) == 3
    assert {s["name"] for s in body["created_shelves"]} == {"staff", "business"}
    client.drain()

    shelves = {c["id"]: c["name"] for c in client.get("/api/collections").json()}
    docs = {d["filename"]: d for d in client.get("/api/documents").json()}
    assert set(docs) == {"holidays.txt", "catalog.txt", "customers.txt"}
    assert shelves[docs["customers.txt"]["collection_id"]] == "staff"
    assert shelves[docs["catalog.txt"]["collection_id"]] == "business"
    assert docs["holidays.txt"]["tags"] == ["hr", "leave"]
    # The batch is gone once confirmed.
    assert client.get(f"/api/intake/{batch_id}").status_code == 404


def test_existing_shelves_take_matching_files_new_versions_and_skip_duplicates(client):
    hr = client.post(
        "/api/collections",
        json={"name": "hr", "embedding_model": client.runtime.settings.embedding_model},
    ).json()["id"]
    _upload(client, "holidays.txt", STAFF_A, hr)

    _, result = _analyze(
        client,
        [
            ("holidays.txt", STAFF_A.replace(b"25", b"27")),  # same name, new content
            ("copy.txt", STAFF_A),  # same content as the stored one
            ("onboarding.txt", STAFF_B),  # similar to the hr shelf
            ("catalog.txt", BIZ_A),  # fits no shelf
        ],
    )
    files = _by_name(result)
    assert files["holidays.txt"]["status"] == "new_version"
    assert files["holidays.txt"]["shelf"] == f"existing:{hr}"
    assert "Same name" in files["holidays.txt"]["reason"]
    assert files["copy.txt"]["status"] == "duplicate"
    assert files["copy.txt"]["include"] is False
    assert files["onboarding.txt"]["shelf"] == f"existing:{hr}"
    assert "holidays.txt" in files["onboarding.txt"]["reason"]
    assert files["catalog.txt"]["shelf"].startswith("new:")


def test_shelf_names_fall_back_to_keywords_when_the_model_gives_no_usable_answer(client):
    # No canned answer: the fake model echoes the prompt, which isn't JSON.
    _, result = _analyze(client, [("a.txt", STAFF_A), ("b.txt", STAFF_B)])
    [shelf] = [s for s in result["shelves"] if not s["existing"]]
    assert shelf["named_by"] == "keywords"
    assert shelf["name"] == "hr"
    assert intake.SHELF_NAME.match(shelf["name"])


def test_a_partial_answer_names_what_it_can_and_keywords_name_the_rest(client):
    client.runtime.fake_llm._responses.append('{"shelves": [{"name": "Not valid!!"}]}')
    _, result = _analyze(client, [("a.txt", STAFF_A), ("c.txt", BIZ_A)])
    named = {s["name"]: s["named_by"] for s in result["shelves"] if not s["existing"]}
    assert named == {"not-valid": "model", "hr": "keywords"}
    assert len(client.runtime.fake_llm.calls) == 1


def test_a_slow_model_is_abandoned_after_the_timeout(runtime, monkeypatch):
    import threading

    release = threading.Event()
    monkeypatch.setattr(intake, "NAMING_TIMEOUT_S", 0.2)
    monkeypatch.setattr(runtime.fake_llm, "generate", lambda *a, **k: release.wait(5) or "{}")
    [(name, _, named_by)] = intake._name_groups(runtime, [([("a.txt", "x")], ["hr"])], set())
    release.set()
    assert (name, named_by) == ("hr", "keywords")


def test_unusable_files_are_left_out_with_a_reason(client):
    _, result = _analyze(client, [("photo.png", b"\x89PNG"), ("blank.txt", b"   \n")])
    files = _by_name(result)
    assert files["photo.png"]["status"] == "unsupported"
    assert files["blank.txt"]["status"] == "empty"
    assert not any(f["include"] for f in files.values())


def test_confirm_rejects_bad_or_clashing_shelf_names(client):
    batch_id, result = _analyze(client, [("a.txt", STAFF_A)])
    ref = result["files"][0]["shelf"]
    assert _confirm(client, batch_id, result, {ref: "Not Valid!"}).status_code == 409
    client.post("/api/collections", json={"name": "taken"})
    assert _confirm(client, batch_id, result, {ref: "taken"}).status_code == 409
    # Still there to fix and retry.
    assert client.get(f"/api/intake/{batch_id}").status_code == 200


def test_confirm_before_the_analysis_finished_is_refused(client):
    batch_id = _start(client, [("a.txt", STAFF_A)])  # job not run yet
    response = client.post(
        f"/api/intake/{batch_id}/confirm",
        json={"files": [{"key": "f0", "include": True, "shelf": "new:g1", "tags": []}]},
    )
    assert response.status_code == 409


def test_cancel_removes_the_staged_files(client):
    batch_id, _ = _analyze(client, [("a.txt", STAFF_A)])
    folder = client.runtime.settings.uploads_dir / "intake" / batch_id
    assert folder.exists()
    assert client.delete(f"/api/intake/{batch_id}").status_code == 204
    assert not folder.exists()
    assert client.get(f"/api/intake/{batch_id}").status_code == 404
    assert client.get("/api/intake/not-a-batch").status_code == 404


def test_batches_left_for_a_day_are_purged(runtime):
    old_id, _ = intake.stage_batch(runtime.settings, [])
    new_id, _ = intake.stage_batch(runtime.settings, [])
    manifest = runtime.settings.uploads_dir / "intake" / old_id / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["created_at"] = (dt.datetime.now(dt.UTC) - dt.timedelta(hours=25)).isoformat()
    manifest.write_text(json.dumps(data), encoding="utf-8")

    assert intake.purge_stale_batches(runtime.settings) == 1
    assert not manifest.parent.exists()
    assert intake.load_batch(runtime.settings, new_id)["state"] == "staged"


class _Vocab:
    """Tag vocabulary with hand-set vectors (2 departments, 1 kind)."""

    dept_names = ["hr", "sales"]
    dept_vecs = np.array([[1.0, 0.0], [0.0, 1.0]])
    kind_names = ["policy"]
    kind_vecs = np.array([[0.0, 1.0]])


def test_tags_come_from_folder_keywords_validity_and_known_spellings():
    tags = intake.suggest_tags(
        "staff-faq.md",
        "Picked/Human Resources/staff-faq.md",
        "Q: How many days off? Valid for Q1 2027.",
        np.array([1.0, 0.0]),
        _Vocab(),
        known_tags={"HR"},
    )
    assert tags == ["human-resources", "HR", "faq", "q1-2027", "2027"]


def test_files_in_the_picked_folder_itself_get_no_folder_tag():
    tags = intake.suggest_tags(
        "notes.txt", "Picked/notes.txt", "text", np.array([1.0, 0.0]), _Vocab(), set()
    )
    assert "picked" not in tags


def test_department_is_left_out_when_too_close_to_call():
    tags = intake.suggest_tags("x.txt", "x.txt", "text", np.array([0.7, 0.7]), _Vocab(), set())
    assert "hr" not in tags and "sales" not in tags


def _shelf_of(result: dict, filename: str) -> str:
    names = {s["ref"]: s for s in result["shelves"]}
    file = next(f for f in result["files"] if f["name"] == filename)
    return names[file["shelf"]]


def test_model_names_go_to_the_group_they_describe_not_the_list_position(client):
    # Asked business first, staff second; the model answers the other way round.
    client.runtime.fake_llm._responses.append(
        '{"shelves": [{"name": "employees", "description": "employee holiday onboarding"},'
        ' {"name": "sales-docs", "description": "sales price catalog customer"}]}'
    )
    _, result = _analyze(client, [("a.txt", STAFF_A), ("c.txt", BIZ_A)])
    assert _shelf_of(result, "a.txt")["name"] == "employees"
    assert _shelf_of(result, "c.txt")["name"] == "sales-docs"


def test_two_names_for_the_same_group_leave_the_other_group_a_keyword_name(client):
    client.runtime.fake_llm._responses.append(
        '{"shelves": [{"name": "employees", "description": "employee holiday"},'
        ' {"name": "staff-rules", "description": "employee onboarding holiday"}]}'
    )
    _, result = _analyze(client, [("a.txt", STAFF_A), ("c.txt", BIZ_A)])
    staff, business = _shelf_of(result, "a.txt"), _shelf_of(result, "c.txt")
    assert staff["named_by"] == "model" and staff["name"] in {"employees", "staff-rules"}
    assert business["named_by"] == "keywords"
