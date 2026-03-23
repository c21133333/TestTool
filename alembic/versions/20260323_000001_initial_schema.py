"""Initial application schema.

Revision ID: 20260323_000001
Revises:
Create Date: 2026-03-23 18:30:00
"""
from __future__ import annotations

from alembic import op

from backend.app.models.base import Base
from backend.app.models.registry import load_model_metadata


revision = "20260323_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    load_model_metadata()
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    load_model_metadata()
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
