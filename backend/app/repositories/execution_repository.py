from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.models.execution import Execution, ExecutionItem, ExecutionScope, ExecutionStatus


class ExecutionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_execution(self, execution: Execution) -> Execution:
        self._session.add(execution)
        self._session.flush()
        return execution

    def save_execution(self, execution: Execution) -> Execution:
        self._session.add(execution)
        self._session.flush()
        return execution

    def add_item(self, item: ExecutionItem) -> ExecutionItem:
        self._session.add(item)
        self._session.flush()
        return item

    def get_execution(self, execution_id: int) -> Execution | None:
        stmt = (
            select(Execution)
            .where(Execution.id == execution_id)
            .options(selectinload(Execution.items), selectinload(Execution.reports))
        )
        return self._session.scalar(stmt)

    def list_executions(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: ExecutionStatus | None = None,
        scope: ExecutionScope | None = None,
        search: str | None = None,
        failed_only: bool = False,
    ) -> tuple[list[Execution], int]:
        stmt = select(Execution).options(selectinload(Execution.reports))
        count_stmt = select(func.count(Execution.id)).select_from(Execution)

        if status is not None:
            stmt = stmt.where(Execution.status == status)
            count_stmt = count_stmt.where(Execution.status == status)
        if scope is not None:
            stmt = stmt.where(Execution.scope == scope)
            count_stmt = count_stmt.where(Execution.scope == scope)
        if search:
            search_value = f"%{search.strip()}%"
            stmt = stmt.where(Execution.target_name.ilike(search_value))
            count_stmt = count_stmt.where(Execution.target_name.ilike(search_value))
        if failed_only:
            failed_condition = Execution.items.any(ExecutionItem.status != "PASS")
            stmt = stmt.where(failed_condition)
            count_stmt = count_stmt.where(failed_condition)

        total = self._session.scalar(count_stmt) or 0
        paged_stmt = stmt.order_by(Execution.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        return list(self._session.scalars(paged_stmt).unique().all()), total

    def get_next_pending_execution(self) -> Execution | None:
        stmt = (
            select(Execution)
            .where(Execution.scope == ExecutionScope.suite, Execution.status == ExecutionStatus.pending)
            .options(selectinload(Execution.items), selectinload(Execution.reports))
            .order_by(Execution.created_at.asc())
        )
        return self._session.scalar(stmt)
