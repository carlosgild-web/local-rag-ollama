"""documents.updated_at

When a document last changed: a new version, or a restore of an earlier one.
The Library shows it next to the date the document was first added. Existing
documents get the date of their newest version.

Revision ID: 0006_document_updated_at
Revises: 0005_portal
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_document_updated_at"
down_revision: str | None = "0005_portal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.execute(
        "UPDATE documents SET updated_at = COALESCE("
        "(SELECT MAX(v.created_at) FROM document_versions v WHERE v.document_id = documents.id),"
        " created_at)"
    )
    with op.batch_alter_table("documents") as batch:
        batch.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("updated_at")
