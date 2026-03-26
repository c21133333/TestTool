"""Add AI chat sessions and messages.

Revision ID: 20260326_000006
Revises: 20260325_000005
Create Date: 2026-03-26 17:20:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260326_000006"
down_revision = "20260325_000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("ai_chat_sessions"):
        op.create_table(
            "ai_chat_sessions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=True),
            sa.Column("chat_mode", sa.String(length=16), nullable=False, server_default="project"),
            sa.Column("title", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("page_path", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("page_title", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("latest_message_preview", sa.Text(), nullable=False, server_default=""),
            sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_ai_chat_sessions_user_id", "ai_chat_sessions", ["user_id"], unique=False)
        op.create_index("ix_ai_chat_sessions_project_id", "ai_chat_sessions", ["project_id"], unique=False)

    if not inspector.has_table("ai_chat_messages"):
        op.create_table(
            "ai_chat_messages",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("session_id", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("content", sa.Text(), nullable=False, server_default=""),
            sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["ai_chat_sessions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_ai_chat_messages_session_id", "ai_chat_messages", ["session_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("ai_chat_messages"):
        for index_name in ["ix_ai_chat_messages_session_id"]:
            if index_name in {item["name"] for item in inspector.get_indexes("ai_chat_messages")}:
                op.drop_index(index_name, table_name="ai_chat_messages")
        op.drop_table("ai_chat_messages")

    if inspector.has_table("ai_chat_sessions"):
        for index_name in ["ix_ai_chat_sessions_project_id", "ix_ai_chat_sessions_user_id"]:
            if index_name in {item["name"] for item in inspector.get_indexes("ai_chat_sessions")}:
                op.drop_index(index_name, table_name="ai_chat_sessions")
        op.drop_table("ai_chat_sessions")
