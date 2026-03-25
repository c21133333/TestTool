from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.schemas.ai_copilot import AiArtifactStatus
from backend.app.services.ai_artifact_service import AiArtifactService
from backend.app.services.ai_test_data_seed_service import AiTestDataSeedService
from backend.app.services.workspace_service import WorkspaceService


class AiTestDataService:
    def __init__(self, session: Session | None = None) -> None:
        self._session = session
        self._seed_service = AiTestDataSeedService()

    def generate_preview(self, context: dict[str, Any]) -> dict[str, Any]:
        snapshot = context.get("input_snapshot") if isinstance(context.get("input_snapshot"), dict) else {}
        warnings: list[str] = []

        if not snapshot.get("recent_success_sample"):
            warnings.append("No recent successful execution sample was found. Test data variants fall back to the saved case body.")

        result = self._seed_service.build_result(snapshot)
        if not result.data_variants:
            warnings.append("No deterministic test data variants could be derived from the current case context.")

        return {"result": result.model_dump(), "warnings": warnings}

    def apply_artifact(
        self,
        artifact_id: str,
        *,
        selected_variant_ids: list[str],
        override_existing: bool = False,
    ):
        if self._session is None:
            raise RuntimeError("AiTestDataService.apply_artifact requires a database session.")
        if not selected_variant_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one test data variant must be selected before apply.",
            )

        artifact_service = AiArtifactService(self._session)
        artifact = artifact_service.accept_artifact(artifact_id)
        if artifact.capability != "test_data":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI artifact capability mismatch.")
        if artifact.case_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI artifact is not bound to a case.")

        available_variants = [
            item for item in (artifact.output_json or {}).get("data_variants", []) if isinstance(item, dict)
        ]
        selected_lookup = {str(item.get("variant_id")): item for item in available_variants if item.get("variant_id")}
        selected_variants = [selected_lookup[variant_id] for variant_id in selected_variant_ids if variant_id in selected_lookup]
        if not selected_variants:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected test data variants were not found in the artifact output.",
            )

        saved_case = WorkspaceService(self._session).save_ai_test_data_variants(
            artifact.case_id,
            selected_variants,
            override_existing=override_existing,
        )
        artifact.status = AiArtifactStatus.applied.value
        artifact_service.save(artifact)
        return saved_case

    def export_artifact(self, artifact_id: str) -> dict[str, Any]:
        if self._session is None:
            raise RuntimeError("AiTestDataService.export_artifact requires a database session.")

        artifact = AiArtifactService(self._session).get_artifact_or_404(artifact_id)
        if artifact.capability != "test_data":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI artifact capability mismatch.")
        if artifact.case_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI artifact is not bound to a case.")

        return {
            "artifact_id": artifact.artifact_id,
            "capability": artifact.capability,
            "case_id": artifact.case_id,
            "status": artifact.status,
            "warnings": list(artifact.warnings_json or []),
            "data_variants": [
                item for item in (artifact.output_json or {}).get("data_variants", []) if isinstance(item, dict)
            ],
        }
