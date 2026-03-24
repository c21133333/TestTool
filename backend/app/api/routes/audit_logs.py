from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import require_roles
from backend.app.core.database import session_scope
from backend.app.core.responses import ApiResponse
from backend.app.models.user import UserRole
from backend.app.schemas.audit_log import AuditLogListData, AuditLogRead
from backend.app.services.audit_log_service import AuditLogService

router = APIRouter()


@router.get("", response_model=ApiResponse[AuditLogListData])
def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    search: str | None = Query(default=None),
    action: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    _: object = Depends(require_roles(UserRole.admin)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AuditLogListData]:
    logs, total = AuditLogService(session).list_logs(
        page=page,
        page_size=page_size,
        search=search,
        action=action,
        actor=actor,
        start_at=start_at,
        end_at=end_at,
    )
    return ApiResponse.ok(
        data=AuditLogListData(
            items=[AuditLogRead.model_validate(log) for log in logs],
            total=total,
            page=page,
            page_size=page_size,
        ),
        message="Audit logs loaded.",
    )
