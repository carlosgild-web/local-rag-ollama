"""Evaluation: golden-set fields, run config and metrics, per-case results

Phase 7 (decision 0019). `eval_cases.expected_source` (one filename) becomes
`expected_sources` (a list); existing values are carried over.

Revision ID: 0008_eval
Revises: 0007_version_origin
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_eval"
down_revision: str | None = "0007_version_origin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("eval_sets") as batch:
        batch.add_column(sa.Column("description", sa.Text(), nullable=False, server_default=""))

    with op.batch_alter_table("eval_cases") as batch:
        batch.add_column(sa.Column("shelf", sa.String(), nullable=True))
        batch.add_column(
            sa.Column("expected_sources", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column("required_facts", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column("expect_not_found", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("kind", sa.String(), nullable=False, server_default=""))
        batch.add_column(sa.Column("variant_group", sa.String(), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, expected_source FROM eval_cases WHERE expected_source IS NOT NULL")
    ).fetchall()
    for case_id, source in rows:
        conn.execute(
            sa.text("UPDATE eval_cases SET expected_sources = :s WHERE id = :id"),
            {"s": json.dumps([source]), "id": case_id},
        )
    with op.batch_alter_table("eval_cases") as batch:
        batch.drop_column("expected_source")

    with op.batch_alter_table("eval_runs") as batch:
        batch.add_column(sa.Column("job_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("label", sa.String(), nullable=False, server_default=""))
        batch.add_column(sa.Column("config", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(
            sa.Column("index_snapshot", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.add_column(sa.Column("metrics", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("finished_at", sa.DateTime(), nullable=True))
        batch.create_foreign_key("fk_eval_runs_job_id", "ingest_jobs", ["job_id"], ["id"])

    op.create_table(
        "eval_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("eval_run_id", sa.Integer(), nullable=False),
        sa.Column("eval_case_id", sa.Integer(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("shelf", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("variant_group", sa.String(), nullable=True),
        sa.Column("expect_not_found", sa.Boolean(), nullable=False),
        sa.Column("expected_sources", sa.JSON(), nullable=False),
        sa.Column("required_facts", sa.JSON(), nullable=False),
        sa.Column("retrieved", sa.JSON(), nullable=False),
        sa.Column("first_relevant_rank", sa.Integer(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("not_found", sa.Boolean(), nullable=True),
        sa.Column("missing_facts", sa.JSON(), nullable=True),
        sa.Column("citation_status", sa.String(), nullable=True),
        sa.Column("cited_sources", sa.JSON(), nullable=True),
        sa.Column("faithfulness", sa.Double(), nullable=True),
        sa.Column("judge_note", sa.Text(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("retrieval_ms", sa.Integer(), nullable=False),
        sa.Column("answer_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["eval_run_id"], ["eval_runs.id"]),
        sa.ForeignKeyConstraint(["eval_case_id"], ["eval_cases.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eval_results_eval_run_id", "eval_results", ["eval_run_id"])


def downgrade() -> None:
    op.drop_index("ix_eval_results_eval_run_id", table_name="eval_results")
    op.drop_table("eval_results")
    with op.batch_alter_table("eval_runs") as batch:
        batch.drop_constraint("fk_eval_runs_job_id", type_="foreignkey")
        for column in ("finished_at", "metrics", "index_snapshot", "config", "label", "job_id"):
            batch.drop_column(column)
    with op.batch_alter_table("eval_cases") as batch:
        batch.add_column(sa.Column("expected_source", sa.String(), nullable=True))
    conn = op.get_bind()
    for case_id, sources in conn.execute(
        sa.text("SELECT id, expected_sources FROM eval_cases")
    ).fetchall():
        first = (json.loads(sources) or [None])[0] if sources else None
        conn.execute(
            sa.text("UPDATE eval_cases SET expected_source = :s WHERE id = :id"),
            {"s": first, "id": case_id},
        )
    with op.batch_alter_table("eval_cases") as batch:
        for column in (
            "variant_group",
            "kind",
            "expect_not_found",
            "required_facts",
            "expected_sources",
            "shelf",
        ):
            batch.drop_column(column)
    with op.batch_alter_table("eval_sets") as batch:
        batch.drop_column("description")
