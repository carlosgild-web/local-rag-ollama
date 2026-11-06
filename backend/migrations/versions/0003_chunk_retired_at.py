"""chunks.retired_at

A reindex used to delete every old chunk, which failed (FOREIGN KEY) for
chunks that saved answers cite in message_sources. Cited chunks are now
retired instead: kept for the answer's history, out of search.

Revision ID: 0003_chunk_retired_at
Revises: 0002_chunk_collection
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_chunk_retired_at"
down_revision: str | None = "0002_chunk_collection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chunks") as batch:
        batch.add_column(sa.Column("retired_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chunks") as batch:
        batch.drop_column("retired_at")
