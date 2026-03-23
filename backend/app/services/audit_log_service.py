from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Session

from backend.app.models.audit_log import AuditLog
from backend.app.models.user import User
from backend.app.repositories.audit_log_repository import AuditLogRepository


class AuditLogService:
    def __init__(self, session: Session) -> None:
        self._logs = AuditLogRepository(session)

    def record(
        self,
        *,
        actor: User | None,
        action: str,
        resource_type: str,
        resource_id: int | str | None,
        summary: str,
        details: dict | None = None,
    ) -> AuditLog:
        return self._logs.create(
            AuditLog(
                user_id=actor.id if actor is not None else None,
                action=action,
                resource_type=resource_type,
                resource_id=str(resource_id or ""),
                summary=summary,
                details_json=details or {},
            )
        )

    def list_logs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        action: str | None = None,
        actor: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> tuple[list[AuditLog], int]:
        return self._logs.list_logs(
            page=page,
            page_size=page_size,
            search=search,
            action=action,
            actor=actor,
            start_at=start_at,
            end_at=end_at,
        )
