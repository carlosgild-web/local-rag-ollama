import io
import json
from pathlib import Path

import pytest

from app.db.models import Document, IngestJob
from app.ingest.uploads import UnsupportedUploadError, safe_filename, stage_upload
from app.jobs import queue
from app.jobs.worker import JobWorker
from app.versioning import service

CORPUS = Path(__file__).parent / "corpus"


def _stage(runtime, filename, content: bytes) -> Path:
    return stage_upload(
        io.BytesIO(content), filename, runtime.settings.uploads_dir, max_bytes=10_000_000
    )


def _enqueue_ingest(db, runtime, collection, filename="notes.txt", content=b"espresso notes"):
    staged = _stage(runtime, filename, content)
    payload = {"staged_path": str(staged), "filename": filename, "collection_id": collection.id}
    return queue.enqueue(db, "ingest", payload), staged


@pytest.fixture
def setup(runtime):
    db = runtime.session_factory()
    collection = service.get_or_create_default_collection(
        db, runtime.vector_store, runtime.settings
    )
    yield db, collection, JobWorker(runtime)
    db.close()


def test_ingest_job_completes_and_removes_staged_upload(runtime, setup):
    db, collection, worker = setup
    job, staged = _enqueue_ingest(db, runtime, collection)

    assert worker.run_once() is True
    db.refresh(job)

    assert job.status == "completed"
    assert job.progress == 1.0
    result = json.loads(job.result)
    assert result["status"] == "ingested"
    assert job.document_id == result["document_id"]
    assert db.get(Document, result["document_id"]).filename == "notes.txt"
    assert not staged.parent.exists()
    assert worker.run_once() is False, "queue is empty"


def test_duplicate_upload_completes_as_skipped(runtime, setup):
    db, collection, worker = setup
    _enqueue_ingest(db, runtime, collection)
    second, _ = _enqueue_ingest(db, runtime, collection, filename="copy.txt")

    worker.run_until_idle()
    db.refresh(second)

    assert second.status == "completed"
    assert json.loads(second.result)["status"] == "skipped_duplicate"


def test_failing_job_retries_automatically_then_fails(runtime, setup):
    db, collection, worker = setup
    job, staged = _enqueue_ingest(db, runtime, collection)
    staged.unlink()  # make the handler fail

    worker.run_until_idle()
    db.refresh(job)

    assert job.status == "failed"
    assert job.retries == runtime.settings.job_max_retries
    assert "FileNotFoundError" in job.error


def test_manual_retry_requeues_failed_job(runtime, setup):
    db, collection, worker = setup
    job, staged = _enqueue_ingest(db, runtime, collection)
    content = staged.read_bytes()
    staged.unlink()
    worker.run_until_idle()

    staged.write_bytes(content)  # the cause is fixed
    queue.retry(db, job.id)
    worker.run_until_idle()
    db.refresh(job)

    assert job.status == "completed"
    assert job.error is None


def test_retry_rejects_jobs_that_did_not_fail(runtime, setup):
    db, collection, worker = setup
    job, _ = _enqueue_ingest(db, runtime, collection)
    with pytest.raises(service.ConflictError):
        queue.retry(db, job.id)


def test_cancel_pending_job_is_immediate_and_worker_skips_it(runtime, setup):
    db, collection, worker = setup
    job, staged = _enqueue_ingest(db, runtime, collection)

    queue.cancel(db, job.id)

    assert db.get(IngestJob, job.id).status == "cancelled"
    assert worker.run_once() is False
    with pytest.raises(service.ConflictError):
        queue.cancel(db, job.id)


def test_cancel_landing_between_claim_read_and_update_is_not_lost(runtime, setup, monkeypatch):
    """Regression (end-to-end test 2026-11-06): the worker read a job as
    pending, a Cancel committed, then the worker overwrote it with running."""
    db, collection, worker = setup
    job, _ = _enqueue_ingest(db, runtime, collection)
    real_transition = queue._transition

    def cancel_first(session, job_id, from_statuses, **values):
        if values.get("status") == "running":
            with runtime.session_factory() as other:  # the API request
                queue.cancel(other, job_id)
        return real_transition(session, job_id, from_statuses, **values)

    monkeypatch.setattr(queue, "_transition", cancel_first)
    assert queue.claim_next(db) is None
    monkeypatch.undo()

    assert queue.get_job(db, job.id).status == "cancelled"
    assert worker.run_once() is False


def test_cancel_of_a_job_claimed_meanwhile_asks_it_to_stop(runtime, setup):
    db, collection, _ = setup
    job, _ = _enqueue_ingest(db, runtime, collection)
    with runtime.session_factory() as worker_db:
        queue.claim_next(worker_db)

    cancelled = queue.cancel(db, job.id)

    assert cancelled.status == "running" and cancelled.cancel_requested is True


def test_retry_is_refused_for_a_job_that_is_not_failed_or_cancelled(runtime, setup):
    db, collection, _ = setup
    job, _ = _enqueue_ingest(db, runtime, collection)
    with pytest.raises(service.ConflictError):
        queue.retry(db, job.id)
    assert queue.get_job(db, job.id).retries == 0


def test_cancel_requested_while_running_stops_at_next_progress_report(runtime, setup):
    db, collection, worker = setup
    for name in ("coffee-brewing-methods.txt", "intro-to-astronomy-telescopes.txt"):
        service.ingest_document(
            db,
            collection=collection,
            source_path=CORPUS / name,
            settings=runtime.settings,
            embedding_client=runtime.embedding_client_for(collection.embedding_model),
            vector_store=runtime.vector_store,
        )
    job = queue.enqueue(db, "reindex_collection", {"collection_id": collection.id})
    # simulate the API flagging the job while the worker is mid-run
    job.cancel_requested = True
    db.commit()

    worker.run_once()
    db.refresh(job)

    assert job.status == "cancelled"


def test_rebuild_job_builds_then_swaps(runtime, setup):
    db, collection, worker = setup
    _enqueue_ingest(db, runtime, collection)
    worker.run_until_idle()

    target = service.start_collection_rebuild(
        db,
        runtime.vector_store,
        collection.id,
        embedding_model="other-model",
        chunk_size_tokens=200,
        chunk_overlap_pct=0.1,
    )
    job = queue.enqueue(
        db,
        "rebuild_collection",
        {"source_collection_id": collection.id, "target_collection_id": target.id},
    )
    worker.run_until_idle()
    db.refresh(job)

    assert job.status == "completed", job.error
    assert service.get_active_collection(db, "default").id == target.id
    assert runtime.vector_store.count(target.chroma_collection) > 0


def test_recover_stale_requeues_running_jobs(runtime, setup):
    db, collection, worker = setup
    job, _ = _enqueue_ingest(db, runtime, collection)
    queue.claim_next(db)  # now "running", as if the process died mid-job

    assert queue.recover_stale(db) == 1
    db.refresh(job)
    assert job.status == "pending"


def test_worker_thread_starts_and_stops(runtime):
    worker = JobWorker(runtime)
    worker.start()
    assert worker.is_running
    worker.stop()
    assert not worker.is_running


def test_stage_upload_rejects_unsupported_types_and_strips_directories(runtime):
    with pytest.raises(UnsupportedUploadError):
        _stage(runtime, "evil.exe", b"x")
    assert safe_filename("..\\..\\secret\\notes.txt") == "notes.txt"
    assert safe_filename("../../etc/notes.md") == "notes.md"


def test_upload_with_no_text_fails_once_with_a_clear_reason(runtime, setup):
    """Regression (end-to-end test 2026-11-06): an empty file became a
    document with 0 chunks that could never answer."""
    db, collection, worker = setup
    job, _ = _enqueue_ingest(db, runtime, collection, filename="blank.txt", content=b"  \n\n \t ")

    worker.run_until_idle()

    job = queue.get_job(db, job.id)
    assert job.status == "failed" and job.retries == 0
    assert "no text could be read from 'blank.txt'" in job.error
    assert db.query(Document).count() == 0


class _DuringEmbed:
    """Wraps the fake embedder to run `action` while the embedding call is
    in flight, i.e. while a real model would still be thinking."""

    def __init__(self, inner, action):
        self.inner, self.action = inner, action

    def embed(self, texts):
        self.action()
        return self.inner.embed(texts)

    @property
    def dimensions(self):
        return self.inner.dimensions


def _hook_embedding(runtime, monkeypatch, action):
    real = runtime.embedding_client_for
    monkeypatch.setattr(runtime, "embedding_client_for", lambda m: _DuringEmbed(real(m), action))


def _write_with_short_timeout(db_path):
    """A second writer that gives up after 0.5 s instead of SQLite's 30 s."""
    import sqlite3

    conn = sqlite3.connect(db_path, timeout=0.5)
    try:
        conn.execute("BEGIN IMMEDIATE")  # takes the write lock or fails
        conn.rollback()
    finally:
        conn.close()


def test_ingest_and_reindex_do_not_hold_the_write_lock_while_embedding(runtime, setup, monkeypatch):
    """Regression (end-to-end test 2026-11-06): Cancel waited 9-12 s because
    indexing kept SQLite's write lock through the embedding call."""
    db, collection, worker = setup
    _hook_embedding(
        runtime, monkeypatch, lambda: _write_with_short_timeout(runtime.settings.db_path)
    )
    job, _ = _enqueue_ingest(db, runtime, collection)

    worker.run_until_idle()  # raises nothing: the hook's write got the lock
    assert queue.get_job(db, job.id).status == "completed", queue.get_job(db, job.id).error

    reindex = queue.enqueue(
        db, "reindex_document", {"document_id": queue.get_job(db, job.id).document_id}
    )
    worker.run_until_idle()
    assert queue.get_job(db, reindex.id).status == "completed", queue.get_job(db, reindex.id).error


def test_cancel_during_an_upload_stops_it_before_anything_is_written(runtime, setup, monkeypatch):
    db, collection, worker = setup

    def click_cancel():
        with runtime.session_factory() as api_db:
            [running] = queue.list_jobs(api_db, status="running")
            queue.cancel(api_db, running.id)

    _hook_embedding(runtime, monkeypatch, click_cancel)
    job, staged = _enqueue_ingest(db, runtime, collection)

    worker.run_until_idle()

    assert queue.get_job(db, job.id).status == "cancelled"
    assert db.query(Document).count() == 0
    assert not staged.exists()
