from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.ai_artifact import AiArtifact


class AiArtifactRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, artifact: AiArtifact) -> AiArtifact:
        self._session.add(artifact)
        self._session.flush()
        self._session.refresh(artifact)
        return artifact

    def save(self, artifact: AiArtifact) -> AiArtifact:
        self._session.add(artifact)
        self._session.flush()
        self._session.refresh(artifact)
        return artifact

    def get_by_artifact_id(self, artifact_id: str) -> AiArtifact | None:
        stmt = select(AiArtifact).where(AiArtifact.artifact_id == artifact_id)
        return self._session.scalar(stmt)

    def list_history(
        self,
        *,
        capability: str | None = None,
        target_type: str | None = None,
        target_id: int | None = None,
    ) -> list[AiArtifact]:
        stmt = select(AiArtifact)
        if capability is not None:
            stmt = stmt.where(AiArtifact.capability == capability)
        if target_type is not None:
            stmt = stmt.where(AiArtifact.target_type == target_type)
        if target_id is not None:
            stmt = stmt.where(AiArtifact.target_id == target_id)
        stmt = stmt.order_by(AiArtifact.created_at.desc(), AiArtifact.id.desc())
        return list(self._session.scalars(stmt).all())
