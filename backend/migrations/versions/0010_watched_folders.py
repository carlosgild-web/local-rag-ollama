"""watched_folders: folders whose new and changed files are ingested

PLAN.md Phase 6, decision 0025.

Revision ID: 0010_watched_folders
Revises: 0009_glossary
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_watched_folders"
down_revision: str | None = "0009_glossary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watched_folders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("recursive", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_scan_at", sa.DateTime(), nullable=True),
        sa.Column("last_file_at", sa.DateTime(), nullable=True),
        sa.Column("files_queued", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("path"),
    )


def downgrade() -> None:
    op.drop_table("watched_folders")
