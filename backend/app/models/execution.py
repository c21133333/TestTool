from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin


class ExecutionStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"


class ExecutionScope(str, enum.Enum):
    case = "case"
    suite = "suite"


class Execution(TimestampMixin, Base):
    __tablename__ = "executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    suite_id: Mapped[int | None] = mapped_column(ForeignKey("suites.id", ondelete="SET NULL"), nullable=True, index=True)
    environment_id: Mapped[int | None] = mapped_column(
        ForeignKey("environments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    triggered_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    scope: Mapped[ExecutionScope] = mapped_column(Enum(ExecutionScope), nullable=False)
    status: Mapped[ExecutionStatus] = mapped_column(Enum(ExecutionStatus), nullable=False, default=ExecutionStatus.pending)
    target_name: Mapped[str] = mapped_column(String(128), nullable=False)
    summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project = relationship("Project", back_populates="executions")
    suite = relationship("Suite", back_populates="executions")
    environment = relationship("Environment")
    triggered_by = relationship("User")
    items = relationship("ExecutionItem", back_populates="execution", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="execution", cascade="all, delete-orphan")


class ExecutionItem(TimestampMixin, Base):
    __tablename__ = "execution_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("executions.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("api_cases.id", ondelete="SET NULL"), nullable=True, index=True)
    order_index: Mapped[int] = mapped_column(nullable=False, default=0)
    case_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    elapsed_ms: Mapped[int | None] = mapped_column(nullable=True)
    request_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    assertion_results_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    failure_message: Mapped[str] = mapped_column(Text, nullable=False, default="")

    execution = relationship("Execution", back_populates="items")
    case = relationship("ApiCase", back_populates="execution_items")
