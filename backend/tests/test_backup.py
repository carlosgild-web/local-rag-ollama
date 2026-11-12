"""Backups (decision 0015): a zip of the database, vectors and original files, made
by the job worker; restore is offline and backs up the current state first."""

import json
import time
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import backup
from app.db.migrate import known_revisions
from app.db.models import AuditLog, Document, IngestJob
from app.db.session import make_engine, make_session_factory
from app.main import _schedule_daily_backup, create_app


@pytest.fixture
def client(runtime):
    app = create_app(runtime, start_worker=False)
    with TestClient(app) as test_client:
        test_client.drain = app.state.worker.run_until_idle
        yield test_client


def _upload(client, name, text):
    shelf = client.get("/api/collections").json()
    shelf_id = (
        shelf[0]["id"]
        if shelf
        else client.post("/api/collections", json={"name": "notes"}).json()["id"]
    )
    response = client.post(
        "/api/documents",
        files=[("files", (name, text.encode(), "text/plain"))],
        data={"collection_id": str(shelf_id)},
    )
    assert response.status_code == 202, response.text
    client.drain()


def test_back_up_now_makes_a_zip_with_everything(client, runtime):
    _upload(client, "kiln.txt", "Safety glasses at every kiln station.")
    response = client.post("/api/backups")
    assert response.status_code == 202
    client.drain()

    [item] = client.get("/api/backups").json()
    assert item["error"] is None
    manifest = item["manifest"]
    assert manifest["reason"] == "manual"
    assert manifest["counts"]["documents"] == 1
    assert manifest["schema_revision"] in known_revisions()
    with zipfile.ZipFile(runtime.settings.backups_dir / item["name"]) as zf:
        names = zf.namelist()
    assert "app.db" in names and "manifest.json" in names
    assert any(n.startswith("files/") and n.endswith(".txt") for n in names)

    download = client.get(f"/api/backups/{item['name']}")
    assert download.status_code == 200 and download.content[:2] == b"PK"

    assert client.delete(f"/api/backups/{item['name']}").status_code == 204
    assert client.get("/api/backups").json() == []
    with runtime.session_factory() as db:
        actions = db.execute(select(AuditLog.action)).scalars().all()
    assert "backup" in actions and "backup_delete" in actions


@pytest.mark.parametrize("name", ["../app.db", "notabackup.zip", "backup-1.zip"])
def test_only_backup_names_are_served(client, name):
    assert client.get(f"/api/backups/{name}").status_code == 404


def test_restore_brings_back_the_data_and_keeps_the_current_state(client, runtime):
    _upload(client, "kiln.txt", "Safety glasses at every kiln station.")
    first = backup.create_backup(runtime.settings)
    time.sleep(1.1)  # backup names have one-second resolution
    _upload(client, "later.txt", "Added after the backup.")
    with runtime.session_factory() as db:
        assert db.execute(select(func.count(Document.id))).scalar_one() == 2

    runtime.engine.dispose()  # a restore runs with the app stopped
    result = backup.restore_backup(runtime.settings, first, known_revisions=known_revisions())
    assert result["restored"]["counts"]["documents"] == 1
    assert result["safety_backup"].endswith("-before-restore.zip")

    engine = make_engine(runtime.settings.db_path)
    with make_session_factory(engine)() as db:
        names = db.execute(select(Document.filename)).scalars().all()
    engine.dispose()
    assert names == ["kiln.txt"]
    safety = backup.read_manifest(runtime.settings.backups_dir / result["safety_backup"])
    assert safety["counts"]["documents"] == 2


def test_restore_is_refused_while_the_app_runs(runtime, tmp_path):
    zip_path = tmp_path / "backup-20260101-000000.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"schema_revision": None}))
        zf.writestr("app.db", b"")
    backup.write_heartbeat(runtime.settings)
    with pytest.raises(backup.BackupError, match="running"):
        backup.restore_backup(runtime.settings, zip_path, known_revisions=known_revisions())
    backup.clear_heartbeat(runtime.settings)
    assert not backup.app_is_running(runtime.settings)


@pytest.mark.parametrize(
    "entries, message",
    [
        ({"app.db": b"x"}, "isn't a backup"),
        ({"manifest.json": b"{}", "files/a.txt": b"x"}, "no database"),
        ({"manifest.json": b"{}", "app.db": b"x", "../evil.txt": b"x"}, "unexpected entry"),
        (
            {"manifest.json": json.dumps({"schema_revision": "9999_future"}), "app.db": b"x"},
            "newer version",
        ),
    ],
)
def test_suspicious_or_foreign_zips_are_refused(runtime, tmp_path, entries, message):
    zip_path = tmp_path / "backup-20260101-000000.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    with pytest.raises(backup.BackupError, match=message):
        backup.restore_backup(runtime.settings, zip_path, known_revisions=known_revisions())


def test_only_the_newest_automatic_backups_are_kept(runtime):
    runtime.settings.backups_dir.mkdir(parents=True, exist_ok=True)
    for day in range(1, 10):
        (runtime.settings.backups_dir / f"backup-202601{day:02d}-000000-auto.zip").write_bytes(b"x")
    (runtime.settings.backups_dir / "backup-20260101-120000.zip").write_bytes(b"x")  # manual
    removed = backup.prune_automatic(runtime.settings, keep=7)
    assert removed == ["backup-20260102-000000-auto.zip", "backup-20260101-000000-auto.zip"]
    assert (runtime.settings.backups_dir / "backup-20260101-120000.zip").exists()


def test_a_daily_backup_is_queued_only_when_needed(client, runtime):
    def queued():
        with runtime.session_factory() as db:
            return db.execute(
                select(func.count(IngestJob.id)).where(IngestJob.job_type == "backup")
            ).scalar_one()

    _schedule_daily_backup(runtime)
    assert queued() == 0  # nothing in the library yet
    _upload(client, "kiln.txt", "Safety glasses at every kiln station.")
    _schedule_daily_backup(runtime)
    _schedule_daily_backup(runtime)  # not twice while one waits
    assert queued() == 1
    client.drain()
    _schedule_daily_backup(runtime)  # the automatic backup is less than a day old
    assert queued() == 1
    [item] = client.get("/api/backups").json()
    assert item["name"].endswith("-auto.zip")

    runtime.settings.backup_keep = 0
    for path in runtime.settings.backups_dir.glob("*.zip"):
        path.unlink()
    _schedule_daily_backup(runtime)
    assert queued() == 1  # turned off


def test_a_restored_backup_does_not_rerun_its_own_backup_job(client, runtime):
    _upload(client, "kiln.txt", "Safety glasses at every kiln station.")
    client.post("/api/backups")
    with runtime.session_factory() as db:  # what the worker sees while it runs the backup
        job = db.execute(select(IngestJob).where(IngestJob.job_type == "backup")).scalar_one()
        job.status = "running"
        db.commit()
    path = backup.create_backup(runtime.settings)
    runtime.engine.dispose()
    backup.restore_backup(runtime.settings, path, known_revisions=known_revisions())
    engine = make_engine(runtime.settings.db_path)
    with make_session_factory(engine)() as db:
        statuses = (
            db.execute(select(IngestJob.status).where(IngestJob.job_type == "backup"))
            .scalars()
            .all()
        )
    engine.dispose()
    assert statuses == ["completed"]
