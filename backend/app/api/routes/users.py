from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import require_roles
from backend.app.core.database import session_scope
from backend.app.core.responses import ApiResponse, PageData
from backend.app.models.user import User, UserRole
from backend.app.schemas.user import UserCreate, UserRead, UserStatusUpdate
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.auth_service import AuthService

router = APIRouter()


@router.get("", response_model=ApiResponse[PageData[UserRead]])
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    _: object = Depends(require_roles(UserRole.admin)),
    session: Session = Depends(session_scope),
) -> ApiResponse[PageData[UserRead]]:
    users, total = AuthService(session).list_users_page(page=page, page_size=page_size)
    return ApiResponse.paginated(
        items=[UserRead.model_validate(user) for user in users],
        total=total,
        page=page,
        page_size=page_size,
        message="Users loaded.",
    )


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


@router.patch("/{user_id}/status", response_model=ApiResponse[UserRead])
def update_user_status(
    user_id: int,
    payload: UserStatusUpdate,
    current_user: User = Depends(require_roles(UserRole.admin)),
    session: Session = Depends(session_scope),
) -> ApiResponse[UserRead]:
    user = AuthService(session).set_user_active_state(user_id, is_active=payload.is_active, actor=current_user)
    action = "user.activate" if payload.is_active else "user.deactivate"
    summary = f"{'Activated' if payload.is_active else 'Deactivated'} user {user.username}"
    AuditLogService(session).record(
        actor=current_user,
        action=action,
        resource_type="user",
        resource_id=user.id,
        summary=summary,
        details={
            "username": user.username,
            "role": user.role.value,
            "is_active": user.is_active,
            "reason": payload.reason.strip(),
        },
    )
    return ApiResponse.ok(data=UserRead.model_validate(user), message="User status updated.")
