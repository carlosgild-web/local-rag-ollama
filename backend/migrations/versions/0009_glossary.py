"""glossary_terms: words people use and the words the documents use

Decision 0021.

Revision ID: 0009_glossary
Revises: 0008_eval
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_glossary"
down_revision: str | None = "0008_eval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "glossary_terms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("term", sa.String(), nullable=False),
        sa.Column("means", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term"),
    )


def downgrade() -> None:
    op.drop_table("glossary_terms")
