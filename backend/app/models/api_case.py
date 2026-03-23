from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin


class ApiCase(TimestampMixin, Base):
    __tablename__ = "api_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    suite_id: Mapped[int] = mapped_column(ForeignKey("suites.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False, default="GET")
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    headers_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    body_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    assertions_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    pre_processors_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    post_processors_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    suite = relationship("Suite", back_populates="cases")
    execution_items = relationship("ExecutionItem", back_populates="case")
