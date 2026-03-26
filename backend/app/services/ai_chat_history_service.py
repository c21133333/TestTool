from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.models.ai_chat_message import AiChatMessage
from backend.app.models.ai_chat_session import AiChatSession
from backend.app.models.project import Project


class AiChatHistoryService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_sessions_for_user(self, user_id: int) -> list[AiChatSession]:
        stmt = (
            select(AiChatSession)
            .where(AiChatSession.user_id == user_id)
            .options(selectinload(AiChatSession.project))
            .order_by(AiChatSession.updated_at.desc(), AiChatSession.id.desc())
        )
        return list(self._session.scalars(stmt).unique().all())

    def get_session_for_user(self, session_id: int, user_id: int) -> AiChatSession:
        stmt = (
            select(AiChatSession)
            .where(AiChatSession.id == session_id, AiChatSession.user_id == user_id)
            .options(selectinload(AiChatSession.project), selectinload(AiChatSession.messages))
        )
        session = self._session.scalar(stmt)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found.")
        return session

    def ensure_session(
        self,
        *,
        user_id: int,
        session_id: int | None,
        chat_mode: str,
        project_id: int | None,
        page_path: str,
        page_title: str,
        seed_title: str,
    ) -> AiChatSession:
        if session_id is not None:
            session = self.get_session_for_user(session_id, user_id)
            session.chat_mode = chat_mode
            session.project_id = project_id
            session.page_path = page_path
            session.page_title = page_title
            self._session.add(session)
            self._session.flush()
            return session

        session = AiChatSession(
            user_id=user_id,
            project_id=project_id,
            chat_mode=chat_mode,
            page_path=page_path,
            page_title=page_title,
            title=self._build_title(seed_title),
        )
        self._session.add(session)
        self._session.flush()
        return session

    def append_turn(
        self,
        *,
        session: AiChatSession,
        user_message: str,
        assistant_message: str,
    ) -> AiChatSession:
        next_order_index = self._next_order_index(session.id)
        payloads = [
            AiChatMessage(session_id=session.id, role="user", content=user_message, order_index=next_order_index),
            AiChatMessage(session_id=session.id, role="assistant", content=assistant_message, order_index=next_order_index + 1),
        ]
        self._session.add_all(payloads)
        session.message_count += len(payloads)
        session.latest_message_preview = self._build_preview(assistant_message or user_message)
        if not session.title:
            session.title = self._build_title(user_message)
        session.updated_at = datetime.now(UTC)
        self._session.add(session)
        self._session.flush()
        return session

    def delete_session_for_user(self, session_id: int, user_id: int) -> AiChatSession:
        session = self.get_session_for_user(session_id, user_id)
        self._session.delete(session)
        self._session.flush()
        return session

    def _next_order_index(self, session_id: int) -> int:
        stmt = select(func.max(AiChatMessage.order_index)).where(AiChatMessage.session_id == session_id)
        current = self._session.scalar(stmt)
        return int(current or 0) + 1

    def _build_title(self, source: str) -> str:
        normalized = " ".join(source.split()).strip()
        if not normalized:
            return "新对话"
        return normalized[:48]

    def _build_preview(self, source: str) -> str:
        normalized = " ".join(source.split()).strip()
        return normalized[:120]

    def project_name_for(self, project_id: int | None) -> str | None:
        if project_id is None:
            return None
        project = self._session.get(Project, project_id)
        return project.name if project is not None else None
