from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.observability import get_logger, log_event
from backend.app.models.scheduled_job import ScheduledJob, ScheduledJobRun, ScheduledJobRunStatus
from backend.app.repositories.execution_repository import ExecutionRepository
from backend.app.repositories.scheduled_job_repository import ScheduledJobRepository
from backend.app.services.execution_service import ExecutionService
from backend.app.services.scheduled_job_service import ScheduledJobService

logger = get_logger("schedule_dispatch")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ScheduleDispatchService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._scheduled_jobs = ScheduledJobRepository(session)
        self._executions = ExecutionRepository(session)
        self._scheduled_job_service = ScheduledJobService(session)
        self._execution_service = ExecutionService(session)

    def dispatch_due_jobs(self, *, now: datetime | None = None, limit: int | None = None) -> list[ScheduledJobRun]:
        resolved_now = now or _utc_now()
        due_jobs = self._scheduled_jobs.list_due_jobs(
            due_at=resolved_now,
            limit=limit or settings.scheduler_batch_size,
        )
        dispatched_runs: list[ScheduledJobRun] = []
        for job in due_jobs:
            dispatched_runs.append(self.dispatch_due_job(job.id, now=resolved_now))
        return dispatched_runs

    def dispatch_due_job(self, job_id: int, *, now: datetime | None = None) -> ScheduledJobRun:
        resolved_now = now or _utc_now()
        job = self._scheduled_job_service.get_job(job_id)
        if not job.enabled or job.next_run_at is None:
            raise ValueError("Scheduled job is not ready for dispatch.")

        planned_run_at = job.next_run_at
        existing_run = self._scheduled_jobs.get_run_by_job_and_planned_run_at(
            scheduled_job_id=job.id,
            planned_run_at=planned_run_at,
        )
        if existing_run is not None:
            return existing_run

        if self._should_skip_for_active_execution(job):
            skipped_run = ScheduledJobRun(
                scheduled_job_id=job.id,
                planned_run_at=planned_run_at,
                triggered_at=resolved_now,
                status=ScheduledJobRunStatus.skipped,
                message="Previous scheduled execution is still pending or running.",
            )
            self._scheduled_jobs.create_run(skipped_run)
            job.next_run_at = self._scheduled_job_service._compute_next_run_at(
                job.cron_expr,
                job.timezone,
                base_time=planned_run_at,
            )
            self._scheduled_jobs.save_job(job)
            self._session.commit()
            log_event(
                logger,
                "schedule.job.skipped",
                level=logging.WARNING,
                scheduled_job_id=job.id,
                planned_run_at=planned_run_at,
                reason="active_execution",
            )
            return skipped_run

        triggered_run = ScheduledJobRun(
            scheduled_job_id=job.id,
            planned_run_at=planned_run_at,
            triggered_at=resolved_now,
            status=ScheduledJobRunStatus.triggered,
            message="Execution queued from scheduler.",
        )
        self._scheduled_jobs.create_run(triggered_run)
        execution = self._execution_service.queue_suite_execution_from_schedule(job, triggered_run)
        job.last_triggered_at = resolved_now
        job.last_triggered_execution_id = execution.id
        job.next_run_at = self._scheduled_job_service._compute_next_run_at(
            job.cron_expr,
            job.timezone,
            base_time=planned_run_at,
        )
        self._scheduled_jobs.save_job(job)
        self._session.commit()
        log_event(
            logger,
            "schedule.job.dispatched",
            scheduled_job_id=job.id,
            scheduled_run_id=triggered_run.id,
            planned_run_at=planned_run_at,
            execution_id=execution.id,
        )
        return triggered_run

    def _should_skip_for_active_execution(self, job: ScheduledJob) -> bool:
        if str(job.concurrency_policy.value if hasattr(job.concurrency_policy, "value") else job.concurrency_policy) != "forbid":
            return False
        active_execution = self._executions.get_latest_active_scheduled_execution(scheduled_job_id=job.id)
        return active_execution is not None
