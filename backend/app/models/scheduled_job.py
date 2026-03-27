from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin


class ScheduledJobConcurrencyPolicy(str, enum.Enum):
    forbid = "forbid"
    allow = "allow"
    replace = "replace"


class ScheduledJobMisfirePolicy(str, enum.Enum):
    skip = "skip"
    fire_once = "fire_once"


class ScheduledJobRunStatus(str, enum.Enum):
    triggered = "triggered"
    skipped = "skipped"
    failed = "failed"


class ScheduledJob(TimestampMixin, Base):
    __tablename__ = "scheduled_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    suite_id: Mapped[int] = mapped_column(ForeignKey("suites.id", ondelete="CASCADE"), nullable=False, index=True)
    environment_id: Mapped[int | None] = mapped_column(
        ForeignKey("environments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cron_expr: Mapped[str] = mapped_column(String(128), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_triggered_execution_id: Mapped[int | None] = mapped_column(
        ForeignKey("executions.id", ondelete="SET NULL"),
        nullable=True,
    )
    concurrency_policy: Mapped[ScheduledJobConcurrencyPolicy] = mapped_column(
        Enum(ScheduledJobConcurrencyPolicy),
        nullable=False,
        default=ScheduledJobConcurrencyPolicy.forbid,
    )
    misfire_policy: Mapped[ScheduledJobMisfirePolicy] = mapped_column(
        Enum(ScheduledJobMisfirePolicy),
        nullable=False,
        default=ScheduledJobMisfirePolicy.skip,
    )
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    project = relationship("Project")
    suite = relationship("Suite")
    environment = relationship("Environment")
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    updated_by = relationship("User", foreign_keys=[updated_by_user_id])
    last_triggered_execution = relationship("Execution", foreign_keys=[last_triggered_execution_id])
    runs = relationship("ScheduledJobRun", back_populates="scheduled_job", cascade="all, delete-orphan")


class ScheduledJobRun(TimestampMixin, Base):
    __tablename__ = "scheduled_job_runs"
    __table_args__ = (
        UniqueConstraint("scheduled_job_id", "planned_run_at", name="uq_scheduled_job_runs_job_planned_run_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scheduled_job_id: Mapped[int] = mapped_column(
        ForeignKey("scheduled_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    planned_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_id: Mapped[int | None] = mapped_column(ForeignKey("executions.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[ScheduledJobRunStatus] = mapped_column(
        Enum(ScheduledJobRunStatus),
        nullable=False,
        default=ScheduledJobRunStatus.triggered,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")

    scheduled_job = relationship("ScheduledJob", back_populates="runs")
    execution = relationship("Execution", foreign_keys=[execution_id])
