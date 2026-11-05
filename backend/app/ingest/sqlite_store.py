"""Minimal SQLite + FTS5 persistence for Phase 1 ingestion.

Phase 3 introduces the full SQLAlchemy models and Alembic migrations for
all tables (collections, document_versions, jobs, audit_log, etc). This
module is the deliberately small subset needed for the CLI's `ingest`
command to write chunks to SQLite and FTS5, and to detect duplicate files
by hash; it will be superseded, not extended, once Phase 3 lands.
"""

import re
import sqlite3
from pathlib import Path

_WORD_RE = re.compile(r"\w+", re.UNICODE)

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


def search_fts(conn: sqlite3.Connection, query: str, top_k: int) -> list[int]:
    """Returns chunk ids ranked by FTS5 relevance, best first."""
    match_query = _build_match_query(query)
    if not match_query:
        return []
    rows = conn.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
        (match_query, top_k),
    ).fetchall()
    return [row["rowid"] for row in rows]


def _build_match_query(text: str) -> str:
    """Quotes each word so FTS5 doesn't choke on user punctuation/operators."""
    words = _WORD_RE.findall(text)
    return " OR ".join(f'"{w}"' for w in words)


def fetch_chunks(conn: sqlite3.Connection, chunk_ids: list[int]) -> dict[int, sqlite3.Row]:
    """Fetches chunk text + citation info (filename, page, heading) by id."""
    if not chunk_ids:
        return {}
    placeholders = ",".join("?" * len(chunk_ids))
    rows = conn.execute(
        f"""
        SELECT chunks.id AS chunk_id, chunks.text, chunks.page, chunks.heading,
               chunks.document_id, documents.filename
        FROM chunks
        JOIN documents ON documents.id = chunks.document_id
        WHERE chunks.id IN ({placeholders})
        """,
        chunk_ids,
    ).fetchall()
    return {row["chunk_id"]: row for row in rows}
