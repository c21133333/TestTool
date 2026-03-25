from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.schemas.ai_copilot import AiArtifactStatus
from backend.app.services.ai_artifact_service import AiArtifactService
from backend.app.services.ai_mock_template_seed_service import AiMockTemplateSeedService
from backend.app.services.workspace_service import WorkspaceService


class AiMockService:
    def __init__(self, session: Session | None = None) -> None:
        self._session = session
        self._seed_service = AiMockTemplateSeedService()

    def generate_preview(self, context: dict[str, Any]) -> dict[str, Any]:
        snapshot = context.get("input_snapshot") if isinstance(context.get("input_snapshot"), dict) else {}
        warnings: list[str] = ["Mock remains export-first in phase3."]

        result = self._seed_service.build_result(snapshot)
        if not result.mock_templates:
            warnings.append("No deterministic mock template could be derived from the current case context.")

        return {"result": result.model_dump(), "warnings": warnings}

    def apply_artifact(
        self,
        artifact_id: str,
        *,
        selected_template_ids: list[str],
        override_existing: bool = False,
    ):
        if self._session is None:
            raise RuntimeError("AiMockService.apply_artifact requires a database session.")
        if not selected_template_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one mock template must be selected before apply.",
            )

        artifact_service = AiArtifactService(self._session)
        artifact = artifact_service.accept_artifact(artifact_id)
        if artifact.capability != "mock":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI artifact capability mismatch.")
        if artifact.case_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI artifact is not bound to a case.")

        available_templates = [
            item for item in (artifact.output_json or {}).get("mock_templates", []) if isinstance(item, dict)
        ]
        selected_lookup = {str(item.get("template_id")): item for item in available_templates if item.get("template_id")}
        selected_templates = [selected_lookup[template_id] for template_id in selected_template_ids if template_id in selected_lookup]
        if not selected_templates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected mock templates were not found in the artifact output.",
            )

        saved_case = WorkspaceService(self._session).save_ai_mock_templates(
            artifact.case_id,
            selected_templates,
            override_existing=override_existing,
        )
        artifact.status = AiArtifactStatus.applied.value
        artifact_service.save(artifact)
        return saved_case

    def export_artifact(self, artifact_id: str) -> dict[str, Any]:
        if self._session is None:
            raise RuntimeError("AiMockService.export_artifact requires a database session.")

        artifact = AiArtifactService(self._session).get_artifact_or_404(artifact_id)
        if artifact.capability != "mock":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI artifact capability mismatch.")
        if artifact.case_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI artifact is not bound to a case.")

        return {
            "artifact_id": artifact.artifact_id,
            "capability": artifact.capability,
            "case_id": artifact.case_id,
            "status": artifact.status,
            "warnings": list(artifact.warnings_json or []),
            "mock_templates": [
                item for item in (artifact.output_json or {}).get("mock_templates", []) if isinstance(item, dict)
            ],
        }
