from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import require_roles
from backend.app.core.database import session_scope
from backend.app.core.responses import ApiResponse
from backend.app.models.user import User, UserRole
from backend.app.schemas.user import UserCreate, UserRead
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.auth_service import AuthService

router = APIRouter()


@router.get("", response_model=ApiResponse[list[UserRead]])
def list_users(
    _: object = Depends(require_roles(UserRole.admin)),
    session: Session = Depends(session_scope),
) -> ApiResponse[list[UserRead]]:
    users = AuthService(session).list_users()
    return ApiResponse.ok(data=[UserRead.model_validate(user) for user in users], message="Users loaded.")


@router.post("", response_model=ApiResponse[UserRead])
def create_user(
    payload: UserCreate,
    current_user: User = Depends(require_roles(UserRole.admin)),
    session: Session = Depends(session_scope),
) -> ApiResponse[UserRead]:
    user = AuthService(session).create_user(payload.username, payload.display_name, payload.password, payload.role)
    AuditLogService(session).record(
        actor=current_user,
        action="user.create",
        resource_type="user",
        resource_id=user.id,
        summary=f"Created user {user.username}",
        details={"username": user.username, "role": user.role.value},
    )
    return ApiResponse.ok(data=UserRead.model_validate(user), message="User created.")
