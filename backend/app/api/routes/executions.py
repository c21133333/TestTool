from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import require_authenticated_user
from backend.app.core.database import session_scope
from backend.app.core.responses import ApiResponse
from backend.app.models.execution import ExecutionScope
from backend.app.models.execution import ExecutionStatus
from backend.app.models.user import User
from backend.app.schemas.execution import ExecutionCreateRequest, ExecutionListData, ExecutionRead
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.execution_service import ExecutionService

router = APIRouter()


@router.get("", response_model=ApiResponse[ExecutionListData])
def list_executions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: ExecutionStatus | None = Query(default=None),
    scope: ExecutionScope | None = Query(default=None),
    search: str | None = Query(default=None),
    failed_only: bool = Query(default=False),
    _: User = Depends(require_authenticated_user),
    session: Session = Depends(session_scope),
) -> ApiResponse[ExecutionListData]:
    executions, total = ExecutionService(session).list_executions(
        page=page,
        page_size=page_size,
        status=status,
        scope=scope,
        search=search,
        failed_only=failed_only,
    )
    return ApiResponse.ok(
        data=ExecutionListData(
            items=[ExecutionRead.model_validate(execution) for execution in executions],
            total=total,
            page=page,
            page_size=page_size,
        ),
        message="Executions loaded.",
    )


@router.get("/{execution_id}", response_model=ApiResponse[ExecutionRead])
def get_execution(
    execution_id: int,
    _: User = Depends(require_authenticated_user),
    session: Session = Depends(session_scope),
) -> ApiResponse[ExecutionRead]:
    execution = ExecutionService(session).get_execution(execution_id)
    return ApiResponse.ok(data=ExecutionRead.model_validate(execution), message="Execution loaded.")


@router.post("", response_model=ApiResponse[ExecutionRead])
def create_execution(
    payload: ExecutionCreateRequest,
    current_user: User = Depends(require_authenticated_user),
    session: Session = Depends(session_scope),
) -> ApiResponse[ExecutionRead]:
    service = ExecutionService(session)
    if payload.scope == ExecutionScope.case:
        execution = service.run_case_now(payload.target_id, payload.environment_id, current_user)
        AuditLogService(session).record(
            actor=current_user,
            action="execution.run_case",
            resource_type="execution",
            resource_id=execution.id,
            summary=f"Executed case {execution.target_name}",
            details={"scope": execution.scope.value, "environment_id": execution.environment_id},
        )
        return ApiResponse.ok(data=ExecutionRead.model_validate(execution), message="Case execution completed.")
    execution = service.queue_suite_execution(payload.target_id, payload.environment_id, current_user)
    AuditLogService(session).record(
        actor=current_user,
        action="execution.queue_suite",
        resource_type="execution",
        resource_id=execution.id,
        summary=f"Queued suite {execution.target_name}",
        details={"scope": execution.scope.value, "environment_id": execution.environment_id},
    )
    return ApiResponse.ok(data=ExecutionRead.model_validate(execution), message="Suite execution queued.")


@router.post("/{execution_id}/cancel", response_model=ApiResponse[ExecutionRead])
def cancel_execution(
    execution_id: int,
    current_user: User = Depends(require_authenticated_user),
    session: Session = Depends(session_scope),
) -> ApiResponse[ExecutionRead]:
    execution = ExecutionService(session).cancel_execution(execution_id)
    AuditLogService(session).record(
        actor=current_user,
        action="execution.cancel",
        resource_type="execution",
        resource_id=execution.id,
        summary=f"Cancel requested for execution {execution.id}",
        details={"status": execution.status.value},
    )
    return ApiResponse.ok(data=ExecutionRead.model_validate(execution), message="Execution cancel request accepted.")


@router.post("/{execution_id}/retry", response_model=ApiResponse[ExecutionRead])
def retry_execution(
    execution_id: int,
    current_user: User = Depends(require_authenticated_user),
    session: Session = Depends(session_scope),
) -> ApiResponse[ExecutionRead]:
    execution = ExecutionService(session).retry_execution(execution_id, current_user)
    AuditLogService(session).record(
        actor=current_user,
        action="execution.retry",
        resource_type="execution",
        resource_id=execution.id,
        summary=f"Retried execution {execution.id}",
        details={"status": execution.status.value},
    )
    return ApiResponse.ok(data=ExecutionRead.model_validate(execution), message="Execution retried.")
