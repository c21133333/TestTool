from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.timezone import to_beijing_isoformat
from backend.app.models.ai_artifact_link import AiArtifactLink
from backend.app.repositories.ai_artifact_link_repository import AiArtifactLinkRepository
from backend.app.schemas.ai_copilot import (
    AiArtifactCapability,
    AiArtifactLineageNodeRead,
    AiArtifactLineageRead,
    AiArtifactStatus,
)
from backend.app.services.ai_artifact_service import AiArtifactService


class AiArtifactLineageService:
    def __init__(self, session: Session) -> None:
        self._artifact_service = AiArtifactService(session)
        self._repository = AiArtifactLinkRepository(session)

    def link_artifact_to_resource(
        self,
        *,
        source_artifact_id: str,
        target_resource_type: str,
        target_resource_key: str,
        link_type: str,
        target_artifact_id: str | None = None,
    ) -> AiArtifactLink:
        self._artifact_service.get_artifact_or_404(source_artifact_id)
        return self._repository.create(
            AiArtifactLink(
                source_artifact_id=source_artifact_id,
                target_artifact_id=(target_artifact_id or "").strip() or None,
                target_resource_type=target_resource_type.strip(),
                target_resource_key=target_resource_key.strip(),
                link_type=link_type.strip() or "derived",
            )
        )

    def get_lineage(self, artifact_id: str) -> AiArtifactLineageRead:
        artifact = self._artifact_service.get_artifact_or_404(artifact_id)
        try:
            capability = AiArtifactCapability(artifact.capability)
            status_value = AiArtifactStatus(artifact.status)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AI artifact lineage is corrupted.") from exc

        items = [
            AiArtifactLineageNodeRead(
                artifact_id=artifact.artifact_id,
                resource_type="ai_artifact",
                resource_key=artifact.artifact_id,
                link_type="root",
                capability=capability,
                status=status_value,
                created_at=to_beijing_isoformat(artifact.created_at),
            )
        ]

        for link in self._repository.list_by_source_artifact_id(artifact_id):
            items.append(
                AiArtifactLineageNodeRead(
                    artifact_id=link.target_artifact_id or "",
                    resource_type=link.target_resource_type,
                    resource_key=link.target_resource_key,
                    link_type=link.link_type,
                    created_at=to_beijing_isoformat(link.created_at),
                )
            )
        return AiArtifactLineageRead(root_artifact_id=artifact_id, items=items)
