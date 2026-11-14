"""The guards around the versioning invariants and the job worker (PLAN.md
Phase 8: "test coverage on versioning and jobs"). Each test names the rule
it protects; coverage showed these branches had no test."""

import json

import pytest

from app.db.models import Collection, Document, IngestJob
from app.jobs import queue
from app.jobs.worker import JobWorker
from app.versioning import profiles, service, watched
from app.versioning.service import ConflictError, NotFoundError


def _shelf(runtime, db, name="shelf"):
    return service.create_collection(db, runtime.vector_store, name=name, embedding_model="fake")


def _ingest(runtime, db, shelf, filename, text, **kwargs):
    path = runtime.settings.data_dir / f"src-{filename}"
    path.write_text(text, encoding="utf-8")
    return service.ingest_document(
        db,
        collection=shelf,
        source_path=path,
        filename=filename,
        settings=runtime.settings,
        embedding_client=runtime.embedding_client_for("fake"),
        vector_store=runtime.vector_store,
        **kwargs,
    )


# --- Invariant 3: soft delete, trash, purge --------------------------------------


def test_purge_refuses_a_document_that_is_not_in_the_trash(runtime):
    with runtime.session_factory() as db:
        doc = _ingest(runtime, db, _shelf(runtime, db), "a.txt", "Alpha.")
        with pytest.raises(ConflictError, match="move it to the trash first"):
            service.purge_document(db, runtime.vector_store, doc.document_id)
        assert db.get(Document, doc.document_id) is not None


def test_trashing_and_restoring_twice_changes_nothing_more(runtime):
    with runtime.session_factory() as db:
        doc = _ingest(runtime, db, _shelf(runtime, db), "a.txt", "Alpha.")
        service.restore_document(db, doc.document_id)  # not trashed: a no-op
        service.soft_delete_document(db, doc.document_id)
        trashed_at = db.get(Document, doc.document_id).trashed_at
        service.soft_delete_document(db, doc.document_id)  # already trashed: a no-op
        assert db.get(Document, doc.document_id).trashed_at == trashed_at


def test_a_new_version_cant_go_into_a_trashed_document(runtime):
    with runtime.session_factory() as db:
        shelf = _shelf(runtime, db)
        doc = _ingest(runtime, db, shelf, "a.txt", "Alpha.")
        service.soft_delete_document(db, doc.document_id)
        with pytest.raises(NotFoundError, match="is gone"):
            _ingest(runtime, db, shelf, "b.txt", "Beta.", into_document_id=doc.document_id)


def test_a_diff_needs_both_versions(runtime):
    with runtime.session_factory() as db:
        doc = _ingest(runtime, db, _shelf(runtime, db), "a.txt", "Alpha.")
        with pytest.raises(NotFoundError):
            service.diff_versions(db, doc.version_id, 99999)


# --- Invariant 4: blue/green collections -----------------------------------------


def test_only_generations_of_the_same_shelf_can_be_swapped(runtime):
    with runtime.session_factory() as db:
        a, b = _shelf(runtime, db, "a"), _shelf(runtime, db, "b")
        with pytest.raises(ConflictError, match="same collection"):
            service.swap_collection(db, a.id, b.id)


def test_an_inactive_generation_cant_be_rebuilt_or_shown_in_the_portal(runtime):
    with runtime.session_factory() as db:
        shelf = _shelf(runtime, db)
        shelf.is_active = False
        db.commit()
        with pytest.raises(ConflictError, match="not active"):
            service.start_collection_rebuild(
                db,
                runtime.vector_store,
                shelf.id,
                embedding_model="other",
                chunk_size_tokens=600,
                chunk_overlap_pct=0.12,
            )
        with pytest.raises(ConflictError, match="not active"):
            service.set_portal_visible(db, shelf.id, False)


def test_an_ingest_job_queued_before_a_swap_lands_in_the_live_generation(runtime):
    with runtime.session_factory() as db:
        old = _shelf(runtime, db, "hr")
        staged = runtime.settings.uploads_dir / "job1" / "policy.txt"
        staged.parent.mkdir(parents=True)
        staged.write_text("Sixteen vacation days.", encoding="utf-8")
        queue.enqueue(
            db,
            "ingest",
            {"staged_path": str(staged), "filename": "policy.txt", "collection_id": old.id},
        )
        # The swap happens while the job waits.
        old.is_active = False
        live = Collection(name="hr", chroma_collection="hr-g2", embedding_model="fake")
        db.add(live)
        db.commit()
        runtime.vector_store.get_or_create_collection(live.chroma_collection, {})
        live_id = live.id

    JobWorker(runtime).run_once()
    with runtime.session_factory() as db:
        doc = db.query(Document).filter_by(filename="policy.txt").one()
        assert doc.collection_id == live_id


# --- Collections for a question ---------------------------------------------------


def test_questions_need_a_shelf(runtime):
    with runtime.session_factory() as db:
        with pytest.raises(ConflictError, match="no collections yet"):
            service.active_collections(db)
        with pytest.raises(ConflictError, match="no collections yet"):
            service.collection_for_question(db, None)
        _shelf(runtime, db, "hr")
        _shelf(runtime, db, "ops")
        with pytest.raises(ConflictError, match="choose a collection"):
            service.collection_for_question(db, None)


# --- Profiles (invariant 6 lives in the prompt) -----------------------------------


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"retrieval_top_k": 0}, "retrieval_top_k"),
        ({"temperature": 3.0}, "temperature"),
        ({"chunk_size_tokens": 10}, "chunk_size_tokens"),
        ({"chunk_overlap_pct": 0.5}, "chunk_overlap_pct"),
        ({"colour": "blue"}, "unknown profile fields"),
    ],
)
def test_profile_values_are_checked(runtime, changes, message):
    with (
        runtime.session_factory() as db,
        pytest.raises(profiles.InvalidProfileError, match=message),
    ):
        profiles.create_profile_version(db, runtime.settings, **changes)


def test_only_the_default_profile_is_created_on_demand(runtime):
    with runtime.session_factory() as db:
        assert profiles.get_active_profile(db, runtime.settings).name == "default"
        with pytest.raises(NotFoundError):
            profiles.get_active_profile(db, runtime.settings, "missing")
        assert profiles.usage_counts(db, []) == {}


# --- The job worker ---------------------------------------------------------------


def test_jobs_left_running_by_a_crash_are_recovered_at_start(runtime):
    with runtime.session_factory() as db:
        crashed = queue.enqueue(db, "backup", {})
        cancelled = queue.enqueue(db, "backup", {})
        for job in (crashed, cancelled):
            job.status = "running"
        cancelled.cancel_requested = True
        db.commit()
        ids = crashed.id, cancelled.id

    worker = JobWorker(runtime)
    worker.start()
    worker.stop()
    with runtime.session_factory() as db:
        assert db.get(IngestJob, ids[0]).status in {"pending", "running", "completed"}
        assert db.get(IngestJob, ids[1]).status == "cancelled"


def test_an_unknown_job_type_fails_cleanly(runtime):
    runtime.settings.job_max_retries = 0  # fail at once instead of retrying
    with runtime.session_factory() as db:
        job = IngestJob(job_type="mystery", payload=json.dumps({}))
        db.add(job)
        db.commit()
        job_id = job.id
    assert JobWorker(runtime).run_once() is True
    with runtime.session_factory() as db:
        job = db.get(IngestJob, job_id)
        assert job.status == "failed" and "no handler" in job.error


def test_the_worker_loop_survives_an_error_and_a_heartbeat_failure(runtime, monkeypatch):
    from app.jobs import worker as worker_module

    runtime.settings.job_poll_interval_seconds = 0.01
    calls = []
    w = JobWorker(runtime)

    def boom():
        calls.append(1)
        if len(calls) >= 3:
            w._stop.set()
        raise RuntimeError("database locked")

    def no_heartbeat(_settings):
        raise OSError("disk full")

    monkeypatch.setattr(w, "run_once", boom)
    monkeypatch.setattr(worker_module.backup, "write_heartbeat", no_heartbeat)
    w._loop()  # returns once the stop flag is set: the errors didn't end it early
    assert len(calls) == 3


# --- Watched folders ---------------------------------------------------------------


def test_changing_a_watched_folder_is_audited(runtime, tmp_path):
    runtime.settings.watch_roots = str(tmp_path)
    folder_path = tmp_path / "in"
    folder_path.mkdir()
    with runtime.session_factory() as db:
        a, b = _shelf(runtime, db, "a"), _shelf(runtime, db, "b")
        folder = watched.add_folder(db, runtime.settings, path=str(folder_path), collection_id=a.id)
        folder = watched.update_folder(db, folder.id, recursive=False, collection_id=b.id)
        assert folder.recursive is False and folder.collection.name == "b"
        with pytest.raises(NotFoundError):
            watched.get_folder(db, 999)
        from app.db.models import AuditLog

        details = [r.detail for r in db.query(AuditLog).filter_by(action="watch_update")]
        assert details and "subfolders left out" in details[0] and "now feeds b" in details[0]


def test_an_unreachable_watched_folder_is_reported(runtime, tmp_path):
    runtime.settings.watch_roots = str(tmp_path)
    folder_path = tmp_path / "usb"
    folder_path.mkdir()
    with runtime.session_factory() as db:
        shelf = _shelf(runtime, db)
        folder = watched.add_folder(
            db, runtime.settings, path=str(folder_path), collection_id=shelf.id
        )
        folder_path.rmdir()  # the drive was unplugged
        result = watched.scan_folder(db, runtime.settings, folder)
        assert result.queued == 0 and "isn't reachable" in folder.last_error
        folder_path.mkdir()  # plugged back in
        watched.scan_folder(db, runtime.settings, folder)
        assert folder.last_error is None
