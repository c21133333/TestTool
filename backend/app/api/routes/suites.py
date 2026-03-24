from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import require_authenticated_user, require_roles
from backend.app.core.database import session_scope
from backend.app.core.responses import ApiResponse, PageData
from backend.app.models.user import User
from backend.app.models.user import UserRole
from backend.app.schemas.workspace import SuiteCreate, SuiteRead
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.workspace_service import WorkspaceService

router = APIRouter()


@router.get("", response_model=ApiResponse[PageData[SuiteRead]])
def list_suites(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    project_id: int | None = Query(default=None),
    _: User = Depends(require_authenticated_user),
    session: Session = Depends(session_scope),
) -> ApiResponse[PageData[SuiteRead]]:
    suites, total = WorkspaceService(session).list_suites_page(page=page, page_size=page_size, project_id=project_id)
    return ApiResponse.paginated(
        items=[SuiteRead.model_validate(suite) for suite in suites],
        total=total,
        page=page,
        page_size=page_size,
        message="Suites loaded.",
    )


@router.post("", response_model=ApiResponse[SuiteRead])
def create_suite(
    payload: SuiteCreate,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[SuiteRead]:
    suite = WorkspaceService(session).create_suite(payload)
    AuditLogService(session).record(
        actor=current_user,
        action="suite.create",
        resource_type="suite",
        resource_id=suite.id,
        summary=f"Created suite {suite.name}",
        details={"name": suite.name, "project_id": suite.project_id},
    )
    return ApiResponse.ok(data=SuiteRead.model_validate(suite), message="Suite created.")


@router.put("/{suite_id}", response_model=ApiResponse[SuiteRead])
def update_suite(
    suite_id: int,
    payload: SuiteCreate,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[SuiteRead]:
    suite = WorkspaceService(session).update_suite(suite_id, payload)
    AuditLogService(session).record(
        actor=current_user,
        action="suite.update",
        resource_type="suite",
        resource_id=suite.id,
        summary=f"Updated suite {suite.name}",
        details={"name": suite.name, "project_id": suite.project_id},
    )
    return ApiResponse.ok(data=SuiteRead.model_validate(suite), message="Suite updated.")


@router.delete("/{suite_id}", response_model=ApiResponse[None])
def delete_suite(
    suite_id: int,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[None]:
    suite = WorkspaceService(session).get_suite(suite_id)
    WorkspaceService(session).delete_suite(suite_id)
    AuditLogService(session).record(
        actor=current_user,
        action="suite.delete",
        resource_type="suite",
        resource_id=suite_id,
        summary=f"Deleted suite {suite.name}",
        details={"name": suite.name, "project_id": suite.project_id},
    )
    return ApiResponse.ok(message="Suite deleted.")
