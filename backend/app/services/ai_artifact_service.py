from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.models.ai_artifact import AiArtifact
from backend.app.repositories.ai_artifact_repository import AiArtifactRepository
from backend.app.schemas.ai_copilot import AiArtifactCapability, AiArtifactStatus, AiArtifactTargetType, AiCallTraceRead


class AiArtifactService:
    def __init__(self, session: Session) -> None:
        self._repository = AiArtifactRepository(session)

    def create_draft_artifact(
        self,
        *,
        capability: AiArtifactCapability,
        target_type: AiArtifactTargetType,
        target_id: int,
        input_json: dict,
        output_json: dict,
        warnings: list[str] | None = None,
        project_id: int | None = None,
        suite_id: int | None = None,
        case_id: int | None = None,
        execution_id: int | None = None,
        report_id: int | None = None,
        provider: str = "",
        model: str = "",
        created_by_user_id: int | None = None,
        call_trace: AiCallTraceRead | dict | None = None,
    ) -> AiArtifact:
        normalized_trace = self._normalize_call_trace(call_trace)
        artifact = AiArtifact(
            artifact_id=uuid4().hex,
            capability=capability.value,
            target_type=target_type.value,
            target_id=target_id,
            project_id=project_id,
            suite_id=suite_id,
            case_id=case_id,
            execution_id=execution_id,
            report_id=report_id,
            input_json=dict(input_json),
            output_json=dict(output_json),
            warnings_json=[str(item) for item in warnings or []],
            status=AiArtifactStatus.draft.value,
            provider=provider.strip(),
            model=model.strip(),
            call_mode=str(normalized_trace.call_mode or "deterministic"),
            latency_ms=normalized_trace.latency_ms,
            failure_category=str(normalized_trace.failure_category or ""),
            trace_json=dict(normalized_trace.trace_json or {}),
            created_by_user_id=created_by_user_id,
        )
        return self._repository.create(artifact)

    def save(self, artifact: AiArtifact) -> AiArtifact:
        return self._repository.save(artifact)

    def get_artifact_or_404(self, artifact_id: str) -> AiArtifact:
        artifact = self._repository.get_by_artifact_id(artifact_id)
        if artifact is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI artifact not found.")
        return artifact

    def accept_artifact(self, artifact_id: str) -> AiArtifact:
        artifact = self.get_artifact_or_404(artifact_id)
        artifact.status = AiArtifactStatus.accepted.value
        return self.save(artifact)

    def reject_artifact(self, artifact_id: str) -> AiArtifact:
        artifact = self.get_artifact_or_404(artifact_id)
        artifact.status = AiArtifactStatus.rejected.value
        return self.save(artifact)

    def mark_applied(self, artifact_id: str) -> AiArtifact:
        artifact = self.get_artifact_or_404(artifact_id)
        artifact.status = AiArtifactStatus.applied.value
        return self.save(artifact)

    def list_history(
        self,
        *,
        capability: AiArtifactCapability,
        target_type: AiArtifactTargetType,
        target_id: int,
    ) -> list[AiArtifact]:
        return self._repository.list_history(
            capability=capability.value,
            target_type=target_type.value,
            target_id=target_id,
        )

    def _normalize_call_trace(self, call_trace: AiCallTraceRead | dict | None) -> AiCallTraceRead:
        if isinstance(call_trace, AiCallTraceRead):
            return call_trace
        if isinstance(call_trace, dict):
            return AiCallTraceRead.model_validate(call_trace)
        return AiCallTraceRead(call_mode="deterministic", trace_json={})
