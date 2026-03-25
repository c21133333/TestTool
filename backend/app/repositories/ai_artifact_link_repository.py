from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.ai_artifact_link import AiArtifactLink


class AiArtifactLinkRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, link: AiArtifactLink) -> AiArtifactLink:
        self._session.add(link)
        self._session.flush()
        self._session.refresh(link)
        return link

    def list_by_source_artifact_id(self, source_artifact_id: str) -> list[AiArtifactLink]:
        stmt = (
            select(AiArtifactLink)
            .where(AiArtifactLink.source_artifact_id == source_artifact_id)
            .order_by(AiArtifactLink.created_at.asc(), AiArtifactLink.id.asc())
        )
        return list(self._session.scalars(stmt).all())
