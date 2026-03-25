from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class AiArtifactLink(TimestampMixin, Base):
    __tablename__ = "ai_artifact_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_artifact_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_artifact_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    target_resource_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_resource_key: Mapped[str] = mapped_column(String(64), nullable=False)
    link_type: Mapped[str] = mapped_column(String(32), nullable=False, default="derived")
