"""chunks.collection_id and ingest_jobs.result

Chunks become per-collection so a blue/green rebuild can index every
version into the new collection while the old one keeps serving queries
(docs/decisions/0003-per-collection-chunks.md).

Revision ID: 0002_chunk_collection
Revises: b080c8f05380
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_chunk_collection"
down_revision: str | None = "b080c8f05380"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chunks") as batch:
        batch.add_column(sa.Column("collection_id", sa.Integer(), nullable=True))

    # Backfill from the owning document's collection.
    op.execute(
        "UPDATE chunks SET collection_id = ("
        " SELECT documents.collection_id FROM document_versions"
        " JOIN documents ON documents.id = document_versions.document_id"
        " WHERE document_versions.id = chunks.version_id)"
    )

    with op.batch_alter_table("chunks") as batch:
        batch.alter_column("collection_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key(
            "fk_chunks_collection_id", "collections", ["collection_id"], ["id"]
        )
        batch.create_index("ix_chunks_collection_id", ["collection_id"])

    with op.batch_alter_table("ingest_jobs") as batch:
        batch.add_column(sa.Column("result", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ingest_jobs") as batch:
        batch.drop_column("result")

    with op.batch_alter_table("chunks") as batch:
        batch.drop_index("ix_chunks_collection_id")
        batch.drop_constraint("fk_chunks_collection_id", type_="foreignkey")
        batch.drop_column("collection_id")
