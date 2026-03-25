"""Create ai_artifacts table.

Revision ID: 20260324_000003
Revises: 20260324_000002
Create Date: 2026-03-24 17:20:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260324_000003"
down_revision = "20260324_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("ai_artifacts"):
        op.create_table(
            "ai_artifacts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("artifact_id", sa.String(length=32), nullable=False),
            sa.Column("capability", sa.String(length=32), nullable=False),
            sa.Column("target_type", sa.String(length=32), nullable=False),
            sa.Column("target_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
            sa.Column("suite_id", sa.Integer(), sa.ForeignKey("suites.id", ondelete="SET NULL"), nullable=True),
            sa.Column("case_id", sa.Integer(), sa.ForeignKey("api_cases.id", ondelete="SET NULL"), nullable=True),
            sa.Column("execution_id", sa.Integer(), sa.ForeignKey("executions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("report_id", sa.Integer(), sa.ForeignKey("reports.id", ondelete="SET NULL"), nullable=True),
            sa.Column("input_json", sa.JSON(), nullable=False),
            sa.Column("output_json", sa.JSON(), nullable=False),
            sa.Column("warnings_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
            sa.Column("provider", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        inspector = sa.inspect(bind)

    index_names = {index["name"] for index in inspector.get_indexes("ai_artifacts")}
    if "ix_ai_artifacts_artifact_id" not in index_names:
        op.create_index("ix_ai_artifacts_artifact_id", "ai_artifacts", ["artifact_id"], unique=True)
    if "ix_ai_artifacts_capability" not in index_names:
        op.create_index("ix_ai_artifacts_capability", "ai_artifacts", ["capability"], unique=False)
    if "ix_ai_artifacts_target_type" not in index_names:
        op.create_index("ix_ai_artifacts_target_type", "ai_artifacts", ["target_type"], unique=False)
    if "ix_ai_artifacts_target_id" not in index_names:
        op.create_index("ix_ai_artifacts_target_id", "ai_artifacts", ["target_id"], unique=False)
    if "ix_ai_artifacts_target_lookup" not in index_names:
        op.create_index("ix_ai_artifacts_target_lookup", "ai_artifacts", ["capability", "target_type", "target_id"], unique=False)
    if "ix_ai_artifacts_project_id" not in index_names:
        op.create_index("ix_ai_artifacts_project_id", "ai_artifacts", ["project_id"], unique=False)
    if "ix_ai_artifacts_suite_id" not in index_names:
        op.create_index("ix_ai_artifacts_suite_id", "ai_artifacts", ["suite_id"], unique=False)
    if "ix_ai_artifacts_case_id" not in index_names:
        op.create_index("ix_ai_artifacts_case_id", "ai_artifacts", ["case_id"], unique=False)
    if "ix_ai_artifacts_execution_id" not in index_names:
        op.create_index("ix_ai_artifacts_execution_id", "ai_artifacts", ["execution_id"], unique=False)
    if "ix_ai_artifacts_report_id" not in index_names:
        op.create_index("ix_ai_artifacts_report_id", "ai_artifacts", ["report_id"], unique=False)
    if "ix_ai_artifacts_status" not in index_names:
        op.create_index("ix_ai_artifacts_status", "ai_artifacts", ["status"], unique=False)
    if "ix_ai_artifacts_created_by_user_id" not in index_names:
        op.create_index("ix_ai_artifacts_created_by_user_id", "ai_artifacts", ["created_by_user_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("ai_artifacts"):
        return

    index_names = {index["name"] for index in inspector.get_indexes("ai_artifacts")}
    for index_name in [
        "ix_ai_artifacts_created_by_user_id",
        "ix_ai_artifacts_status",
        "ix_ai_artifacts_report_id",
        "ix_ai_artifacts_execution_id",
        "ix_ai_artifacts_case_id",
        "ix_ai_artifacts_suite_id",
        "ix_ai_artifacts_project_id",
        "ix_ai_artifacts_target_lookup",
        "ix_ai_artifacts_target_id",
        "ix_ai_artifacts_target_type",
        "ix_ai_artifacts_capability",
        "ix_ai_artifacts_artifact_id",
    ]:
        if index_name in index_names:
            op.drop_index(index_name, table_name="ai_artifacts")
    op.drop_table("ai_artifacts")
