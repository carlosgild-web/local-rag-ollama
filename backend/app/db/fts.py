"""Raw-SQL helpers for the chunks_fts FTS5 virtual table.

SQLAlchemy's ORM has no concept of FTS5 virtual tables, so these go
through the session's connection directly rather than the ORM. `chunks_fts`
is an external-content table (content='chunks'), so removing a row needs
its old text value supplied via the 'delete' command.
"""

import re

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

CHUNKS_FTS_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, content='chunks', "
    "content_rowid='id')"
)

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def create_fts_table(engine: Engine) -> None:
    """Creates the chunks_fts virtual table outside of a migration (tests only;
    the migration executes CHUNKS_FTS_DDL directly via op.execute)."""
    with engine.begin() as conn:
        conn.exec_driver_sql(CHUNKS_FTS_DDL)


def index_chunk(db: Session, chunk_id: int, chunk_text: str) -> None:
    db.execute(
        text("INSERT INTO chunks_fts (rowid, text) VALUES (:id, :text)"),
        {"id": chunk_id, "text": chunk_text},
    )


def remove_chunk(db: Session, chunk_id: int, chunk_text: str) -> None:
    db.execute(
        text("INSERT INTO chunks_fts (chunks_fts, rowid, text) VALUES ('delete', :id, :text)"),
        {"id": chunk_id, "text": chunk_text},
    )


def search(db: Session, query: str, top_k: int) -> list[int]:
    """Returns chunk ids ranked by FTS5 relevance, best first."""
    match_query = build_match_query(query)
    if not match_query:
        return []
    rows = db.execute(
        text("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH :q ORDER BY rank LIMIT :k"),
        {"q": match_query, "k": top_k},
    ).fetchall()
    return [row[0] for row in rows]


def build_match_query(value: str) -> str:
    """Quotes each word so FTS5 doesn't choke on user punctuation/operators."""
    words = _WORD_RE.findall(value)
    return " OR ".join(f'"{w}"' for w in words)
