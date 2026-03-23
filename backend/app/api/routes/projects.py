from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import require_authenticated_user, require_roles
from backend.app.core.database import session_scope
from backend.app.core.responses import ApiResponse
from backend.app.models.user import User
from backend.app.models.user import UserRole
from backend.app.schemas.workspace import ProjectCreate, ProjectRead
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.workspace_service import WorkspaceService

router = APIRouter()


@router.get("", response_model=ApiResponse[list[ProjectRead]])
def list_projects(
    _: User = Depends(require_authenticated_user),
    session: Session = Depends(session_scope),
) -> ApiResponse[list[ProjectRead]]:
    projects = WorkspaceService(session).list_projects()
    return ApiResponse.ok(data=[ProjectRead.model_validate(project) for project in projects], message="Projects loaded.")


@router.post("", response_model=ApiResponse[ProjectRead])
def create_project(
    payload: ProjectCreate,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[ProjectRead]:
    project = WorkspaceService(session).create_project(payload)
    AuditLogService(session).record(
        actor=current_user,
        action="project.create",
        resource_type="project",
        resource_id=project.id,
        summary=f"Created project {project.name}",
        details={"name": project.name},
    )
    return ApiResponse.ok(data=ProjectRead.model_validate(project), message="Project created.")


@router.put("/{project_id}", response_model=ApiResponse[ProjectRead])
def update_project(
    project_id: int,
    payload: ProjectCreate,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[ProjectRead]:
    project = WorkspaceService(session).update_project(project_id, payload)
    AuditLogService(session).record(
        actor=current_user,
        action="project.update",
        resource_type="project",
        resource_id=project.id,
        summary=f"Updated project {project.name}",
        details={"name": project.name},
    )
    return ApiResponse.ok(data=ProjectRead.model_validate(project), message="Project updated.")


@router.delete("/{project_id}", response_model=ApiResponse[None])
def delete_project(
    project_id: int,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[None]:
    project = WorkspaceService(session).get_project(project_id)
    WorkspaceService(session).delete_project(project_id)
    AuditLogService(session).record(
        actor=current_user,
        action="project.delete",
        resource_type="project",
        resource_id=project_id,
        summary=f"Deleted project {project.name}",
        details={"name": project.name},
    )
    return ApiResponse.ok(message="Project deleted.")
