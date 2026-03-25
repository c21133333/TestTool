from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class AiCaseHistory(TimestampMixin, Base):
    __tablename__ = "ai_case_histories"

    id: Mapped[int] = mapped_column(primary_key=True)
    history_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    suite_name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    base_url: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    prompt_preset: Mapped[str] = mapped_column(String(32), nullable=False, default="balanced")
    prompt_hints: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prompt_hints_effective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    markdown_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    batch_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
