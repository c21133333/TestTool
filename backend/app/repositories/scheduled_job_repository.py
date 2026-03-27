from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.models.scheduled_job import ScheduledJob, ScheduledJobRun


class ScheduledJobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_job(self, job: ScheduledJob) -> ScheduledJob:
        self._session.add(job)
        self._session.flush()
        return job

    def save_job(self, job: ScheduledJob) -> ScheduledJob:
        self._session.add(job)
        self._session.flush()
        return job

    def get_job(self, job_id: int) -> ScheduledJob | None:
        stmt = (
            select(ScheduledJob)
            .where(ScheduledJob.id == job_id)
            .options(
                selectinload(ScheduledJob.suite),
                selectinload(ScheduledJob.environment),
                selectinload(ScheduledJob.last_triggered_execution),
            )
        )
        return self._session.scalar(stmt)

    def list_jobs_page(
        self,
        *,
        page: int,
        page_size: int,
        project_id: int | None = None,
        suite_id: int | None = None,
        enabled: bool | None = None,
        search: str | None = None,
    ) -> tuple[list[ScheduledJob], int]:
        stmt = (
            select(ScheduledJob)
            .options(
                selectinload(ScheduledJob.suite),
                selectinload(ScheduledJob.environment),
                selectinload(ScheduledJob.last_triggered_execution),
            )
            .order_by(ScheduledJob.created_at.desc(), ScheduledJob.id.desc())
        )
        count_stmt = select(func.count(ScheduledJob.id)).select_from(ScheduledJob)

        if project_id is not None:
            stmt = stmt.where(ScheduledJob.project_id == project_id)
            count_stmt = count_stmt.where(ScheduledJob.project_id == project_id)
        if suite_id is not None:
            stmt = stmt.where(ScheduledJob.suite_id == suite_id)
            count_stmt = count_stmt.where(ScheduledJob.suite_id == suite_id)
        if enabled is not None:
            stmt = stmt.where(ScheduledJob.enabled == enabled)
            count_stmt = count_stmt.where(ScheduledJob.enabled == enabled)
        if search:
            search_value = f"%{search.strip()}%"
            stmt = stmt.where(ScheduledJob.name.ilike(search_value))
            count_stmt = count_stmt.where(ScheduledJob.name.ilike(search_value))

        total = int(self._session.scalar(count_stmt) or 0)
        paged_stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        return list(self._session.scalars(paged_stmt).unique().all()), total

    def create_run(self, run: ScheduledJobRun) -> ScheduledJobRun:
        self._session.add(run)
        self._session.flush()
        return run

    def list_runs(self, scheduled_job_id: int, *, limit: int = 20) -> list[ScheduledJobRun]:
        stmt = (
            select(ScheduledJobRun)
            .where(ScheduledJobRun.scheduled_job_id == scheduled_job_id)
            .options(selectinload(ScheduledJobRun.execution))
            .order_by(ScheduledJobRun.planned_run_at.desc(), ScheduledJobRun.id.desc())
            .limit(limit)
        )
        return list(self._session.scalars(stmt).unique().all())

    def list_due_jobs(self, *, due_at: datetime, limit: int) -> list[ScheduledJob]:
        stmt = (
            select(ScheduledJob)
            .where(
                ScheduledJob.enabled.is_(True),
                ScheduledJob.next_run_at.is_not(None),
                ScheduledJob.next_run_at <= due_at,
            )
            .options(
                selectinload(ScheduledJob.suite),
                selectinload(ScheduledJob.environment),
                selectinload(ScheduledJob.last_triggered_execution),
            )
            .order_by(ScheduledJob.next_run_at.asc(), ScheduledJob.id.asc())
            .limit(limit)
        )
        return list(self._session.scalars(stmt).unique().all())

    def get_run_by_job_and_planned_run_at(self, *, scheduled_job_id: int, planned_run_at: datetime) -> ScheduledJobRun | None:
        stmt = (
            select(ScheduledJobRun)
            .where(
                ScheduledJobRun.scheduled_job_id == scheduled_job_id,
                ScheduledJobRun.planned_run_at == planned_run_at,
            )
            .options(selectinload(ScheduledJobRun.execution))
        )
        return self._session.scalar(stmt)
