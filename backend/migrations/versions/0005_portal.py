"""collections.portal_visible and chat_sessions.channel

The employee portal (decision 0010): Luna searches every active shelf that
is visible in the portal, and its chats are kept apart from the admin
console's history.

Revision ID: 0005_portal
Revises: 0004_session_collection
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_portal"
down_revision: str | None = "0004_session_collection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("collections") as batch:
        batch.add_column(
            sa.Column("portal_visible", sa.Boolean(), nullable=False, server_default=sa.true())
        )
    with op.batch_alter_table("chat_sessions") as batch:
        batch.add_column(sa.Column("channel", sa.String(), nullable=False, server_default="admin"))
        batch.create_index("ix_chat_sessions_channel", ["channel"])


def downgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch:
        batch.drop_index("ix_chat_sessions_channel")
        batch.drop_column("channel")
    with op.batch_alter_table("collections") as batch:
        batch.drop_column("portal_visible")
