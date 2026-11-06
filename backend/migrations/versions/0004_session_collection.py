"""chat_sessions.collection_id

Each chat session remembers the shelf it searches, so follow-up questions
and a reopened chat use the same one. Before, a page refresh reset the UI
picker and a question without a shelf silently created an empty 'default'
collection (end-to-end test 2026-11-06).

Revision ID: 0004_session_collection
Revises: 0003_chunk_retired_at
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_session_collection"
down_revision: str | None = "0003_chunk_retired_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch:
        batch.add_column(sa.Column("collection_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_chat_sessions_collection_id", "collections", ["collection_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch:
        batch.drop_constraint("fk_chat_sessions_collection_id", type_="foreignkey")
        batch.drop_column("collection_id")
