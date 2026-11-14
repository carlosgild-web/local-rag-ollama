"""Watched folders (decision 0025): configuration, scanning, the watcher
thread's settle logic, and that every file goes through the normal ingest."""

import time

import pytest
from fastapi.testclient import TestClient

from app.db.models import Collection, Document
from app.ingest.watcher import FolderWatcher
from app.main import create_app
from app.versioning import service, watched


@pytest.fixture
def client(runtime):
    app = create_app(runtime, start_worker=False)
    with TestClient(app) as test_client:
        test_client.drain = app.state.worker.run_until_idle
        test_client.app_state = app.state
        yield test_client


@pytest.fixture
def shelf(runtime):
    with runtime.session_factory() as db:
        return service.create_collection(
            db, runtime.vector_store, name="inbox", embedding_model="fake"
        ).id


@pytest.fixture
def folder(tmp_path):
    root = tmp_path / "watched"
    root.mkdir()
    return root


def _add(client, path, shelf, **extra):
    response = client.post(
        "/api/watched-folders", json={"path": str(path), "collection_id": shelf, **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _scan(client, folder_id):
    response = client.post(f"/api/watched-folders/{folder_id}/scan")
    assert response.status_code == 200, response.text
    client.drain()
    return response.json()


def _documents(runtime):
    with runtime.session_factory() as db:
        return {d.filename: d for d in db.query(Document).all()}


# --- Configuration ---------------------------------------------------------------


def test_add_list_and_audit(client, folder, shelf):
    added = _add(client, folder, shelf)
    assert added["collection_name"] == "inbox" and added["recursive"] is True
    assert added["state"] == "stopped", "the test app doesn't run the watcher thread"

    body = client.get("/api/watched-folders").json()
    assert body["mode"] == "events" and [f["id"] for f in body["folders"]] == [added["id"]]
    audit = client.get("/api/audit", params={"action": "watch_add"}).json()
    assert audit and "inbox" in audit[0]["detail"]


def test_state_comes_from_the_watcher_thread(client, folder, shelf):
    from app.ingest.watcher import WatcherStatus

    added = _add(client, folder, shelf)
    watcher = client.app_state.watcher

    def state_with(status):
        watcher.status = lambda: status
        return client.get("/api/watched-folders").json()["folders"][0]

    assert state_with(WatcherStatus(True, "events"))["state"] == "starting"
    assert state_with(WatcherStatus(True, "events", watching={added["id"]}))["state"] == "watching"
    failed = state_with(WatcherStatus(True, "events", errors={added["id"]: "can't watch it"}))
    assert failed["state"] == "error" and failed["error"] == "can't watch it"


@pytest.mark.parametrize(
    "path, code",
    [
        ("relative/folder", 422),
        ("{missing}", 422),
        ("{data}", 422),
        ("{data}/files", 422),
    ],
)
def test_bad_paths_are_refused(client, runtime, tmp_path, shelf, path, code):
    path = path.format(missing=tmp_path / "nope", data=runtime.settings.data_dir)
    response = client.post("/api/watched-folders", json={"path": path, "collection_id": shelf})
    assert response.status_code == code, response.text


def test_overlapping_folders_and_unknown_shelves_are_refused(client, folder, shelf):
    (folder / "sub").mkdir()
    _add(client, folder, shelf)
    inner = client.post(
        "/api/watched-folders", json={"path": str(folder / "sub"), "collection_id": shelf}
    )
    assert inner.status_code == 409
    again = client.post("/api/watched-folders", json={"path": str(folder), "collection_id": shelf})
    assert again.status_code == 409
    other = folder.parent / "other"
    other.mkdir()
    unknown = client.post("/api/watched-folders", json={"path": str(other), "collection_id": 999})
    assert unknown.status_code == 404


def test_pause_resume_and_remove_keep_the_documents(client, runtime, folder, shelf):
    (folder / "a.txt").write_text("Alpha notes about kilns.")
    added = _add(client, folder, shelf)
    _scan(client, added["id"])

    paused = client.patch(f"/api/watched-folders/{added['id']}", json={"enabled": False}).json()
    assert paused["enabled"] is False and paused["state"] == "paused"
    with runtime.session_factory() as db:
        assert watched.folder_for(db, folder / "a.txt") is None, "a paused folder takes nothing"

    assert client.delete(f"/api/watched-folders/{added['id']}").status_code == 204
    assert client.get("/api/watched-folders").json()["folders"] == []
    assert "a.txt" in _documents(runtime)
    actions = {e["action"] for e in client.get("/api/audit").json()}
    assert {"watch_add", "watch_update", "watch_remove"} <= actions


# --- Scanning --------------------------------------------------------------------


def test_scan_ingests_new_files_through_the_normal_pipeline(client, runtime, folder, shelf):
    (folder / "a.txt").write_text("Alpha notes about kilns.")
    (folder / "sub").mkdir()
    (folder / "sub" / "b.md").write_text("# Beta\nGlaze recipes.")
    (folder / "~$lock.docx").write_text("office lock file")
    (folder / "draft.txt.part").write_text("half a download")
    (folder / "photo.png").write_bytes(b"\x89PNG")
    added = _add(client, folder, shelf)

    assert _scan(client, added["id"]) == {"queued": 2, "known": 0, "skipped": 0}
    docs = _documents(runtime)
    assert set(docs) == {"a.txt", "sub/b.md"}, "subfolder files keep their folder in the name"
    with runtime.session_factory() as db:
        version = service.get_version(db, docs["a.txt"].id, docs["a.txt"].active_version_id)
        assert version.note == f"From watched folder {added['path']}"

    assert _scan(client, added["id"]) == {"queued": 0, "known": 2, "skipped": 0}
    listed = client.get("/api/watched-folders").json()["folders"][0]
    assert listed["files_queued"] == 2 and listed["last_scan_at"] is not None


def test_a_changed_file_becomes_a_new_version(client, runtime, folder, shelf):
    path = folder / "policy.txt"
    path.write_text("Twelve vacation days.")
    added = _add(client, folder, shelf)
    _scan(client, added["id"])
    path.write_text("Sixteen vacation days.")
    assert _scan(client, added["id"])["queued"] == 1

    doc = _documents(runtime)["policy.txt"]
    with runtime.session_factory() as db:
        versions = db.get(Document, doc.id).versions
        assert [v.version_number for v in versions] == [1, 2]


def test_a_deleted_file_keeps_its_document(client, runtime, folder, shelf):
    path = folder / "gone.txt"
    path.write_text("Soon deleted.")
    added = _add(client, folder, shelf)
    _scan(client, added["id"])
    path.unlink()
    _scan(client, added["id"])
    doc = _documents(runtime)["gone.txt"]
    assert doc.trashed_at is None and doc.active_version_id is not None


def test_non_recursive_folders_leave_subfolders_out(client, runtime, folder, shelf):
    (folder / "top.txt").write_text("Top level.")
    (folder / "sub").mkdir()
    (folder / "sub" / "deep.txt").write_text("Deeper.")
    added = _add(client, folder, shelf, recursive=False)
    assert _scan(client, added["id"])["queued"] == 1
    with runtime.session_factory() as db:
        assert watched.folder_for(db, folder / "sub" / "deep.txt") is None
    assert set(_documents(runtime)) == {"top.txt"}


def test_a_file_waiting_in_the_queue_is_not_queued_twice(client, folder, shelf):
    (folder / "a.txt").write_text("Alpha.")
    added = _add(client, folder, shelf)
    first = client.post(f"/api/watched-folders/{added['id']}/scan").json()
    second = client.post(f"/api/watched-folders/{added['id']}/scan").json()  # not drained
    assert first["queued"] == 1 and second == {"queued": 0, "known": 1, "skipped": 0}


def test_files_go_to_the_live_shelf_after_a_blue_green_swap(runtime, folder, shelf):
    with runtime.session_factory() as db:
        added = watched.add_folder(db, runtime.settings, path=str(folder), collection_id=shelf)
        old = db.get(Collection, shelf)
        old.is_active = False
        new = Collection(
            name="inbox",
            chroma_collection="inbox-g2",
            embedding_model="fake",
            chunk_size_tokens=old.chunk_size_tokens,
            chunk_overlap_pct=old.chunk_overlap_pct,
        )
        db.add(new)
        db.commit()
        assert watched.shelf_of(db, added).id == new.id


def test_too_large_files_are_skipped_with_a_note(client, runtime, folder, shelf):
    runtime.settings.max_upload_mb = 0  # every non-empty file is "too large"
    (folder / "big.txt").write_text("x" * 100)
    added = _add(client, folder, shelf)
    assert _scan(client, added["id"]) == {"queued": 0, "known": 0, "skipped": 1}
    listed = client.get("/api/watched-folders").json()["folders"][0]
    assert "over 0 MB" in listed["error"]


# --- The watcher thread ----------------------------------------------------------


def test_a_file_is_queued_only_after_it_stops_changing(runtime, folder, shelf):
    with runtime.session_factory() as db:
        watched.add_folder(db, runtime.settings, path=str(folder), collection_id=shelf)
    runtime.settings.watch_settle_seconds = 2.0
    watcher = FolderWatcher(runtime)
    path = folder / "new.txt"
    path.write_text("First draft.")
    watcher.file_changed(path)
    watcher.file_changed(folder / ".hidden.txt")  # never tracked

    t0 = time.monotonic()
    assert watcher.process_pending(t0) == [], "too soon after the event"
    assert watcher.process_pending(t0 + 3) == [], "first look: remember size and time"
    path.write_text("First draft, longer now.")  # still being written
    assert watcher.process_pending(t0 + 6) == []
    assert watcher.process_pending(t0 + 9) == [path]
    with runtime.session_factory() as db:
        assert db.query(Document).count() == 0, "only queued; the job worker ingests"
        jobs = [j for j in service_jobs(db) if j.job_type == "ingest"]
        assert len(jobs) == 1


def service_jobs(db):
    from app.jobs import queue

    return queue.list_jobs(db)


def test_the_running_watcher_picks_up_a_new_file(runtime, folder, shelf):
    """End to end with watchdog's polling observer (what Docker uses)."""
    runtime.settings.watch_polling = True
    runtime.settings.watch_poll_seconds = 0.1
    runtime.settings.watch_settle_seconds = 0.1
    with runtime.session_factory() as db:
        watched.add_folder(db, runtime.settings, path=str(folder), collection_id=shelf)
    watcher = FolderWatcher(runtime, tick_seconds=0.05)
    watcher.start()
    try:
        deadline = time.monotonic() + 5
        while not watcher.status().watching and time.monotonic() < deadline:
            time.sleep(0.05)
        assert watcher.status().mode == "polling" and watcher.status().watching
        (folder / "dropped.txt").write_text("Dropped in while the app runs.")
        queued = []
        while not queued and time.monotonic() < deadline + 5:
            time.sleep(0.1)
            with runtime.session_factory() as db:
                queued = [j for j in service_jobs(db) if j.job_type == "ingest"]
        assert queued, "the watcher queued the new file"
    finally:
        watcher.stop()
    assert not watcher.status().running


def test_startup_scan_catches_files_added_while_off(runtime, folder, shelf):
    (folder / "while-off.txt").write_text("Added while the app was off.")
    with runtime.session_factory() as db:
        watched.add_folder(db, runtime.settings, path=str(folder), collection_id=shelf)
    runtime.settings.watch_polling = True
    watcher = FolderWatcher(runtime, tick_seconds=0.05)
    watcher.start()
    try:
        deadline = time.monotonic() + 5
        queued = []
        while not queued and time.monotonic() < deadline:
            time.sleep(0.05)
            with runtime.session_factory() as db:
                queued = [j for j in service_jobs(db) if j.job_type == "ingest"]
        assert queued
    finally:
        watcher.stop()
