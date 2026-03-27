from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import require_authenticated_user, require_roles
from backend.app.core.database import session_scope
from backend.app.core.responses import ApiResponse, PageData
from backend.app.models.user import User, UserRole
from backend.app.schemas.scheduled_job import ScheduledJobCreate, ScheduledJobRead, ScheduledJobRunRead, ScheduledJobUpdate
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.scheduled_job_service import ScheduledJobService

router = APIRouter()


@router.get("", response_model=ApiResponse[PageData[ScheduledJobRead]])
def list_scheduled_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    project_id: int | None = Query(default=None),
    suite_id: int | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    _: User = Depends(require_authenticated_user),
    session: Session = Depends(session_scope),
) -> ApiResponse[PageData[ScheduledJobRead]]:
    jobs, total = ScheduledJobService(session).list_jobs(
        page=page,
        page_size=page_size,
        project_id=project_id,
        suite_id=suite_id,
        enabled=enabled,
        search=search,
    )
    return ApiResponse.paginated(
        items=[ScheduledJobRead.model_validate(job) for job in jobs],
        total=total,
        page=page,
        page_size=page_size,
        message="Scheduled jobs loaded.",
    )


@router.post("", response_model=ApiResponse[ScheduledJobRead])
def create_scheduled_job(
    payload: ScheduledJobCreate,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[ScheduledJobRead]:
    job = ScheduledJobService(session).create_job(payload, actor=current_user)
    AuditLogService(session).record(
        actor=current_user,
        action="scheduled_job.create",
        resource_type="scheduled_job",
        resource_id=job.id,
        summary=f"Created scheduled job {job.name}",
        details={
            "project_id": job.project_id,
            "suite_id": job.suite_id,
            "environment_id": job.environment_id,
            "cron_expr": job.cron_expr,
            "enabled": job.enabled,
        },
    )
    return ApiResponse.ok(data=ScheduledJobRead.model_validate(job), message="Scheduled job created.")


@router.put("/{job_id}", response_model=ApiResponse[ScheduledJobRead])
def update_scheduled_job(
    job_id: int,
    payload: ScheduledJobUpdate,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[ScheduledJobRead]:
    job = ScheduledJobService(session).update_job(job_id, payload, actor=current_user)
    AuditLogService(session).record(
        actor=current_user,
        action="scheduled_job.update",
        resource_type="scheduled_job",
        resource_id=job.id,
        summary=f"Updated scheduled job {job.name}",
        details={
            "project_id": job.project_id,
            "suite_id": job.suite_id,
            "environment_id": job.environment_id,
            "cron_expr": job.cron_expr,
            "enabled": job.enabled,
        },
    )
    return ApiResponse.ok(data=ScheduledJobRead.model_validate(job), message="Scheduled job updated.")


@router.post("/{job_id}/enable", response_model=ApiResponse[ScheduledJobRead])
def enable_scheduled_job(
    job_id: int,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[ScheduledJobRead]:
    job = ScheduledJobService(session).enable_job(job_id, actor=current_user)
    AuditLogService(session).record(
        actor=current_user,
        action="scheduled_job.enable",
        resource_type="scheduled_job",
        resource_id=job.id,
        summary=f"Enabled scheduled job {job.name}",
        details={"enabled": job.enabled, "next_run_at": job.next_run_at.isoformat() if job.next_run_at else None},
    )
    return ApiResponse.ok(data=ScheduledJobRead.model_validate(job), message="Scheduled job enabled.")


@router.post("/{job_id}/disable", response_model=ApiResponse[ScheduledJobRead])
def disable_scheduled_job(
    job_id: int,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[ScheduledJobRead]:
    job = ScheduledJobService(session).disable_job(job_id, actor=current_user)
    AuditLogService(session).record(
        actor=current_user,
        action="scheduled_job.disable",
        resource_type="scheduled_job",
        resource_id=job.id,
        summary=f"Disabled scheduled job {job.name}",
        details={"enabled": job.enabled},
    )
    return ApiResponse.ok(data=ScheduledJobRead.model_validate(job), message="Scheduled job disabled.")


@router.post("/{job_id}/trigger", response_model=ApiResponse[ScheduledJobRunRead])
def trigger_scheduled_job(
    job_id: int,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[ScheduledJobRunRead]:
    run, execution = ScheduledJobService(session).trigger_job(job_id, actor=current_user)
    AuditLogService(session).record(
        actor=current_user,
        action="scheduled_job.trigger",
        resource_type="scheduled_job",
        resource_id=job_id,
        summary=f"Triggered scheduled job {job_id}",
        details={"scheduled_run_id": run.id, "execution_id": execution.id},
    )
    return ApiResponse.ok(data=ScheduledJobRunRead.model_validate(run), message="Scheduled job triggered.")


@router.get("/{job_id}/runs", response_model=ApiResponse[list[ScheduledJobRunRead]])
def list_scheduled_job_runs(
    job_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_authenticated_user),
    session: Session = Depends(session_scope),
) -> ApiResponse[list[ScheduledJobRunRead]]:
    runs = ScheduledJobService(session).list_runs(job_id, limit=limit)
    return ApiResponse.ok(
        data=[ScheduledJobRunRead.model_validate(run) for run in runs],
        message="Scheduled job runs loaded.",
    )
