from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin


class AiChatSession(TimestampMixin, Base):
    __tablename__ = "ai_chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    chat_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="project")
    title: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    page_path: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    page_title: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    latest_message_preview: Mapped[str] = mapped_column(Text, nullable=False, default="")
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    user = relationship("User", back_populates="ai_chat_sessions")
    project = relationship("Project")
    messages = relationship("AiChatMessage", back_populates="session", cascade="all, delete-orphan")
