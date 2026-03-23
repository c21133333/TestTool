from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.models.audit_log import AuditLog
from backend.app.models.user import User


class AuditLogRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, audit_log: AuditLog) -> AuditLog:
        self._session.add(audit_log)
        self._session.flush()
        return audit_log

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
        stmt = select(AuditLog).options(selectinload(AuditLog.user)).outerjoin(AuditLog.user)
        count_stmt = select(func.count(AuditLog.id)).select_from(AuditLog).outerjoin(AuditLog.user)
        filters = []

        if search:
            search_value = f"%{search.strip()}%"
            filters.append(
                or_(
                    AuditLog.summary.ilike(search_value),
                    AuditLog.action.ilike(search_value),
                    AuditLog.resource_type.ilike(search_value),
                    AuditLog.resource_id.ilike(search_value),
                    User.username.ilike(search_value),
                    User.display_name.ilike(search_value),
                )
            )
        if action:
            filters.append(AuditLog.action == action)
        if actor:
            filters.append(User.username == actor)
        if start_at is not None:
            filters.append(AuditLog.created_at >= start_at)
        if end_at is not None:
            filters.append(AuditLog.created_at <= end_at)

        if filters:
            stmt = stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)

        total = self._session.scalar(count_stmt) or 0
        paged_stmt = stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        return list(self._session.scalars(paged_stmt).all()), total
