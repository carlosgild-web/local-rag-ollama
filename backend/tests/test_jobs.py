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
