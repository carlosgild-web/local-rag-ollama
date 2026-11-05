"""Minimal SQLite + FTS5 persistence for Phase 1 ingestion.

Phase 3 introduces the full SQLAlchemy models and Alembic migrations for
all tables (collections, document_versions, jobs, audit_log, etc). This
module is the deliberately small subset needed for the CLI's `ingest`
command to write chunks to SQLite and FTS5, and to detect duplicate files
by hash; it will be superseded, not extended, once Phase 3 lands.
"""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    ext TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    page INTEGER,
    heading TEXT,
    token_estimate INTEGER NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, content='chunks', content_rowid='id'
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def find_document_by_hash(conn: sqlite3.Connection, sha256: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM documents WHERE sha256 = ?", (sha256,)).fetchone()


def insert_document(
    conn: sqlite3.Connection,
    *,
    path: str,
    filename: str,
    sha256: str,
    ext: str,
    ingested_at: str,
) -> int:
    cursor = conn.execute(
        "INSERT INTO documents (path, filename, sha256, ext, ingested_at) VALUES (?, ?, ?, ?, ?)",
        (path, filename, sha256, ext, ingested_at),
    )
    return cursor.lastrowid


def insert_chunks(conn: sqlite3.Connection, document_id: int, chunks: list[dict]) -> list[int]:
    chunk_ids = []
    for chunk in chunks:
        cursor = conn.execute(
            "INSERT INTO chunks (document_id, chunk_index, text, page, heading, token_estimate) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                document_id,
                chunk["chunk_index"],
                chunk["text"],
                chunk["page"],
                chunk["heading"],
                chunk["token_estimate"],
            ),
        )
        chunk_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO chunks_fts (rowid, text) VALUES (?, ?)", (chunk_id, chunk["text"])
        )
        chunk_ids.append(chunk_id)
    return chunk_ids
