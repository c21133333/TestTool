"""Add telemetry fields to ai_artifacts.

Revision ID: 20260325_000005
Revises: 20260325_000004
Create Date: 2026-03-25 13:20:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260325_000005"
down_revision = "20260325_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("ai_artifacts")} if inspector.has_table("ai_artifacts") else set()
    if "call_mode" not in columns:
        op.add_column("ai_artifacts", sa.Column("call_mode", sa.String(length=32), nullable=False, server_default="deterministic"))
    if "latency_ms" not in columns:
        op.add_column("ai_artifacts", sa.Column("latency_ms", sa.Integer(), nullable=True))
    if "failure_category" not in columns:
        op.add_column("ai_artifacts", sa.Column("failure_category", sa.String(length=64), nullable=False, server_default=""))
    if "trace_json" not in columns:
        op.add_column("ai_artifacts", sa.Column("trace_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("ai_artifacts"):
        return
    columns = {column["name"] for column in inspector.get_columns("ai_artifacts")}
    for column_name in ["trace_json", "failure_category", "latency_ms", "call_mode"]:
        if column_name in columns:
            op.drop_column("ai_artifacts", column_name)
