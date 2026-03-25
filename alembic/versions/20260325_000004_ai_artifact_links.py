"""Create ai_artifact_links table.

Revision ID: 20260325_000004
Revises: 20260324_000003
Create Date: 2026-03-25 11:30:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260325_000004"
down_revision = "20260324_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("ai_artifact_links"):
        op.create_table(
            "ai_artifact_links",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_artifact_id", sa.String(length=32), nullable=False),
            sa.Column("target_artifact_id", sa.String(length=32), nullable=True),
            sa.Column("target_resource_type", sa.String(length=32), nullable=False),
            sa.Column("target_resource_key", sa.String(length=64), nullable=False),
            sa.Column("link_type", sa.String(length=32), nullable=False, server_default="derived"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        inspector = sa.inspect(bind)

    index_names = {index["name"] for index in inspector.get_indexes("ai_artifact_links")}
    if "ix_ai_artifact_links_source_artifact_id" not in index_names:
        op.create_index("ix_ai_artifact_links_source_artifact_id", "ai_artifact_links", ["source_artifact_id"], unique=False)
    if "ix_ai_artifact_links_target_artifact_id" not in index_names:
        op.create_index("ix_ai_artifact_links_target_artifact_id", "ai_artifact_links", ["target_artifact_id"], unique=False)
    if "ix_ai_artifact_links_target_resource_type" not in index_names:
        op.create_index("ix_ai_artifact_links_target_resource_type", "ai_artifact_links", ["target_resource_type"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("ai_artifact_links"):
        return

    index_names = {index["name"] for index in inspector.get_indexes("ai_artifact_links")}
    for index_name in [
        "ix_ai_artifact_links_target_resource_type",
        "ix_ai_artifact_links_target_artifact_id",
        "ix_ai_artifact_links_source_artifact_id",
    ]:
        if index_name in index_names:
            op.drop_index(index_name, table_name="ai_artifact_links")
    op.drop_table("ai_artifact_links")
