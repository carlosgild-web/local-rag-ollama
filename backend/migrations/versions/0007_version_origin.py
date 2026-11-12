"""document_versions.origin and edited_by

How a version came in: "upload" (a file was added) or "edit" (its text was
changed in the app's editor), and who edited it. Existing versions are uploads.

Revision ID: 0007_version_origin
Revises: 0006_document_updated_at
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_version_origin"
down_revision: str | None = "0006_document_updated_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("document_versions") as batch:
        batch.add_column(sa.Column("origin", sa.String(), nullable=False, server_default="upload"))
        batch.add_column(sa.Column("edited_by", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("document_versions") as batch:
        batch.drop_column("edited_by")
        batch.drop_column("origin")
