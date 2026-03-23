from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import require_authenticated_user, require_roles
from backend.app.core.database import session_scope
from backend.app.core.responses import ApiResponse
from backend.app.models.user import User
from backend.app.models.user import UserRole
from backend.app.schemas.workspace import EnvironmentCreate, EnvironmentRead
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.workspace_service import WorkspaceService

router = APIRouter()


@router.get("", response_model=ApiResponse[list[EnvironmentRead]])
def list_environments(
    project_id: int | None = Query(default=None),
    _: User = Depends(require_authenticated_user),
    session: Session = Depends(session_scope),
) -> ApiResponse[list[EnvironmentRead]]:
    environments = WorkspaceService(session).list_environments(project_id)
    return ApiResponse.ok(
        data=[EnvironmentRead.model_validate(environment) for environment in environments],
        message="Environments loaded.",
    )


@router.post("", response_model=ApiResponse[EnvironmentRead])
def create_environment(
    payload: EnvironmentCreate,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[EnvironmentRead]:
    environment = WorkspaceService(session).create_environment(payload)
    AuditLogService(session).record(
        actor=current_user,
        action="environment.create",
        resource_type="environment",
        resource_id=environment.id,
        summary=f"Created environment {environment.name}",
        details={"name": environment.name, "project_id": environment.project_id},
    )
    return ApiResponse.ok(data=EnvironmentRead.model_validate(environment), message="Environment created.")


@router.put("/{environment_id}", response_model=ApiResponse[EnvironmentRead])
def update_environment(
    environment_id: int,
    payload: EnvironmentCreate,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[EnvironmentRead]:
    environment = WorkspaceService(session).update_environment(environment_id, payload)
    AuditLogService(session).record(
        actor=current_user,
        action="environment.update",
        resource_type="environment",
        resource_id=environment.id,
        summary=f"Updated environment {environment.name}",
        details={"name": environment.name, "project_id": environment.project_id},
    )
    return ApiResponse.ok(data=EnvironmentRead.model_validate(environment), message="Environment updated.")


@router.delete("/{environment_id}", response_model=ApiResponse[None])
def delete_environment(
    environment_id: int,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[None]:
    environment = WorkspaceService(session).get_environment(environment_id)
    WorkspaceService(session).delete_environment(environment_id)
    AuditLogService(session).record(
        actor=current_user,
        action="environment.delete",
        resource_type="environment",
        resource_id=environment_id,
        summary=f"Deleted environment {environment.name}",
        details={"name": environment.name, "project_id": environment.project_id},
    )
    return ApiResponse.ok(message="Environment deleted.")
