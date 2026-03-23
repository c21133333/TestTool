from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin


class Suite(TimestampMixin, Base):
    __tablename__ = "suites"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    project = relationship("Project", back_populates="suites")
    cases = relationship("ApiCase", back_populates="suite", cascade="all, delete-orphan")
    executions = relationship("Execution", back_populates="suite")
