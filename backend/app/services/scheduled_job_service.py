from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import CroniterBadCronError, CroniterBadDateError, croniter
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.models.execution import ExecutionTriggerSource
from backend.app.models.scheduled_job import ScheduledJob, ScheduledJobRun, ScheduledJobRunStatus
from backend.app.models.user import User
from backend.app.repositories.scheduled_job_repository import ScheduledJobRepository
from backend.app.schemas.scheduled_job import ScheduledJobCreate, ScheduledJobUpdate
from backend.app.services.execution_service import ExecutionService
from backend.app.services.workspace_service import WorkspaceService


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ScheduledJobService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._scheduled_jobs = ScheduledJobRepository(session)
        self._workspace = WorkspaceService(session)

    def list_jobs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        project_id: int | None = None,
        suite_id: int | None = None,
        enabled: bool | None = None,
        search: str | None = None,
    ) -> tuple[list[ScheduledJob], int]:
        return self._scheduled_jobs.list_jobs_page(
            page=page,
            page_size=page_size,
            project_id=project_id,
            suite_id=suite_id,
            enabled=enabled,
            search=search,
        )

    def get_job(self, job_id: int) -> ScheduledJob:
        job = self._scheduled_jobs.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled job not found.")
        return job

    def create_job(self, payload: ScheduledJobCreate, *, actor: User | None) -> ScheduledJob:
        normalized_name = payload.name.strip()
        if not normalized_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Scheduled job name is required.")
        _, suite, environment = self._validate_schedule_scope(
            project_id=payload.project_id,
            suite_id=payload.suite_id,
            environment_id=payload.environment_id,
        )
        timezone = self._validate_timezone(payload.timezone)
        next_run_at = self._compute_next_run_at(
            cron_expr=payload.cron_expr,
            timezone=timezone.key,
        ) if payload.enabled else None
        job = ScheduledJob(
            project_id=payload.project_id,
            suite_id=suite.id,
            environment_id=environment.id if environment is not None else None,
            name=normalized_name,
            description=payload.description.strip(),
            cron_expr=payload.cron_expr.strip(),
            timezone=timezone.key,
            enabled=payload.enabled,
            next_run_at=next_run_at,
            concurrency_policy=payload.concurrency_policy,
            misfire_policy=payload.misfire_policy,
            created_by_user_id=actor.id if actor is not None else None,
            updated_by_user_id=actor.id if actor is not None else None,
        )
        return self._scheduled_jobs.create_job(job)

    def update_job(self, job_id: int, payload: ScheduledJobUpdate, *, actor: User | None) -> ScheduledJob:
        job = self.get_job(job_id)
        normalized_name = payload.name.strip()
        if not normalized_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Scheduled job name is required.")
        _, suite, environment = self._validate_schedule_scope(
            project_id=payload.project_id,
            suite_id=payload.suite_id,
            environment_id=payload.environment_id,
        )
        timezone = self._validate_timezone(payload.timezone)
        job.project_id = payload.project_id
        job.suite_id = suite.id
        job.environment_id = environment.id if environment is not None else None
        job.name = normalized_name
        job.description = payload.description.strip()
        job.cron_expr = payload.cron_expr.strip()
        job.timezone = timezone.key
        job.enabled = payload.enabled
        job.next_run_at = self._compute_next_run_at(job.cron_expr, job.timezone) if job.enabled else None
        job.concurrency_policy = payload.concurrency_policy
        job.misfire_policy = payload.misfire_policy
        job.updated_by_user_id = actor.id if actor is not None else None
        return self._scheduled_jobs.save_job(job)

    def enable_job(self, job_id: int, *, actor: User | None) -> ScheduledJob:
        job = self.get_job(job_id)
        job.enabled = True
        job.next_run_at = self._compute_next_run_at(job.cron_expr, job.timezone)
        job.updated_by_user_id = actor.id if actor is not None else None
        return self._scheduled_jobs.save_job(job)

    def disable_job(self, job_id: int, *, actor: User | None) -> ScheduledJob:
        job = self.get_job(job_id)
        job.enabled = False
        job.next_run_at = None
        job.updated_by_user_id = actor.id if actor is not None else None
        return self._scheduled_jobs.save_job(job)

    def list_runs(self, job_id: int, *, limit: int = 20) -> list[ScheduledJobRun]:
        self.get_job(job_id)
        return self._scheduled_jobs.list_runs(job_id, limit=limit)

    def trigger_job(self, job_id: int, *, actor: User | None) -> tuple[ScheduledJobRun, object]:
        job = self.get_job(job_id)
        planned_run_at = _utc_now()
        run = ScheduledJobRun(
            scheduled_job_id=job.id,
            planned_run_at=planned_run_at,
            triggered_at=planned_run_at,
            status=ScheduledJobRunStatus.triggered,
            message="Execution queued from scheduled job trigger.",
        )
        self._scheduled_jobs.create_run(run)
        execution = ExecutionService(self._session).queue_suite_execution_from_schedule(job, run)
        execution.triggered_by_user_id = actor.id if actor is not None else None
        execution.trigger_source = ExecutionTriggerSource.schedule
        job.last_triggered_at = planned_run_at
        job.last_triggered_execution_id = execution.id
        job.updated_by_user_id = actor.id if actor is not None else None
        self._scheduled_jobs.save_job(job)
        self._session.commit()
        return run, execution

    def _validate_schedule_scope(
        self,
        *,
        project_id: int,
        suite_id: int,
        environment_id: int | None,
    ):
        project = self._workspace.get_project(project_id)
        suite = self._workspace.get_suite(suite_id)
        if suite.project_id != project.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Suite must belong to the selected project.")
        environment = None
        if environment_id is not None:
            environment = self._workspace.get_environment(environment_id)
            if environment.project_id != project.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Environment must belong to the selected project.",
                )
        return project, suite, environment

    def _validate_timezone(self, timezone_name: str) -> ZoneInfo:
        normalized = timezone_name.strip()
        if not normalized:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Timezone is required.")
        try:
            return ZoneInfo(normalized)
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid timezone.") from exc

    def _compute_next_run_at(
        self,
        cron_expr: str,
        timezone: str,
        *,
        base_time: datetime | None = None,
    ) -> datetime:
        normalized_cron = cron_expr.strip()
        if not normalized_cron:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cron expression is required.")
        zone = self._validate_timezone(timezone)
        current_local_time = _normalize_utc(base_time or _utc_now()).astimezone(zone)
        try:
            next_local_time = croniter(normalized_cron, current_local_time).get_next(datetime)
        except (CroniterBadCronError, CroniterBadDateError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cron expression.") from exc
        if next_local_time.tzinfo is None:
            next_local_time = next_local_time.replace(tzinfo=zone)
        return next_local_time.astimezone(UTC)
