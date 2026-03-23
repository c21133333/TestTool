from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import require_authenticated_user, require_roles
from backend.app.core.database import session_scope
from backend.app.core.responses import ApiResponse
from backend.app.models.user import User
from backend.app.models.user import UserRole
from backend.app.schemas.workspace import ApiCaseCreate, ApiCaseRead
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.workspace_service import WorkspaceService

router = APIRouter()


@router.get("", response_model=ApiResponse[list[ApiCaseRead]])
def list_cases(
    suite_id: int | None = Query(default=None),
    _: User = Depends(require_authenticated_user),
    session: Session = Depends(session_scope),
) -> ApiResponse[list[ApiCaseRead]]:
    cases = WorkspaceService(session).list_cases(suite_id)
    return ApiResponse.ok(data=[ApiCaseRead.model_validate(case) for case in cases], message="Cases loaded.")


@router.post("", response_model=ApiResponse[ApiCaseRead])
def create_case(
    payload: ApiCaseCreate,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[ApiCaseRead]:
    case = WorkspaceService(session).create_case(payload)
    AuditLogService(session).record(
        actor=current_user,
        action="case.create",
        resource_type="case",
        resource_id=case.id,
        summary=f"Created case {case.name}",
        details={"name": case.name, "suite_id": case.suite_id, "method": case.method},
    )
    return ApiResponse.ok(data=ApiCaseRead.model_validate(case), message="Case created.")


@router.put("/{case_id}", response_model=ApiResponse[ApiCaseRead])
def update_case(
    case_id: int,
    payload: ApiCaseCreate,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[ApiCaseRead]:
    case = WorkspaceService(session).update_case(case_id, payload)
    AuditLogService(session).record(
        actor=current_user,
        action="case.update",
        resource_type="case",
        resource_id=case.id,
        summary=f"Updated case {case.name}",
        details={"name": case.name, "suite_id": case.suite_id, "method": case.method},
    )
    return ApiResponse.ok(data=ApiCaseRead.model_validate(case), message="Case updated.")


@router.delete("/{case_id}", response_model=ApiResponse[None])
def delete_case(
    case_id: int,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[None]:
    case = WorkspaceService(session).get_case(case_id)
    WorkspaceService(session).delete_case(case_id)
    AuditLogService(session).record(
        actor=current_user,
        action="case.delete",
        resource_type="case",
        resource_id=case_id,
        summary=f"Deleted case {case.name}",
        details={"name": case.name, "suite_id": case.suite_id, "method": case.method},
    )
    return ApiResponse.ok(message="Case deleted.")
