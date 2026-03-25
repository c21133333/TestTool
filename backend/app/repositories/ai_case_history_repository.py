from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.ai_case_history import AiCaseHistory


class AiCaseHistoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, history: AiCaseHistory) -> AiCaseHistory:
        self._session.add(history)
        self._session.flush()
        self._session.refresh(history)
        return history

    def get_by_history_id(self, history_id: str) -> AiCaseHistory | None:
        stmt = select(AiCaseHistory).where(AiCaseHistory.history_id == history_id)
        return self._session.scalar(stmt)

    def list_history(self, *, project_id: int | None = None) -> list[AiCaseHistory]:
        stmt = select(AiCaseHistory).order_by(AiCaseHistory.created_at.desc(), AiCaseHistory.id.desc())
        if project_id is not None:
            stmt = stmt.where(AiCaseHistory.project_id == project_id)
        return list(self._session.scalars(stmt).all())
