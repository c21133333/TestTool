"""Create ai_case_histories table.

Revision ID: 20260324_000002
Revises: 20260323_000001
Create Date: 2026-03-24 16:20:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260324_000002"
down_revision = "20260323_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("ai_case_histories"):
        op.create_table(
            "ai_case_histories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("history_id", sa.String(length=32), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("suite_name", sa.String(length=128), nullable=False),
            sa.Column("provider", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("base_url", sa.String(length=1024), nullable=False, server_default=""),
            sa.Column("prompt_preset", sa.String(length=32), nullable=False, server_default="balanced"),
            sa.Column("prompt_hints", sa.Text(), nullable=False, server_default=""),
            sa.Column("prompt_hints_effective", sa.Text(), nullable=False, server_default=""),
            sa.Column("markdown_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("batch_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        inspector = sa.inspect(bind)

    index_names = {index["name"] for index in inspector.get_indexes("ai_case_histories")}
    if "ix_ai_case_histories_history_id" not in index_names:
        op.create_index("ix_ai_case_histories_history_id", "ai_case_histories", ["history_id"], unique=True)
    if "ix_ai_case_histories_project_id" not in index_names:
        op.create_index("ix_ai_case_histories_project_id", "ai_case_histories", ["project_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("ai_case_histories"):
        return

    index_names = {index["name"] for index in inspector.get_indexes("ai_case_histories")}
    if "ix_ai_case_histories_project_id" in index_names:
        op.drop_index("ix_ai_case_histories_project_id", table_name="ai_case_histories")
    if "ix_ai_case_histories_history_id" in index_names:
        op.drop_index("ix_ai_case_histories_history_id", table_name="ai_case_histories")
    op.drop_table("ai_case_histories")
