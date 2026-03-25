from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.schemas.ai_copilot import (
    AiArtifactCapability,
    AiArtifactHistoryListRead,
    AiArtifactRead,
    AiCallTraceRead,
    AiArtifactStatus,
    AiArtifactTargetType,
    AiCopilotPreviewResponse,
)
from backend.app.services.ai_artifact_service import AiArtifactService
from backend.app.services.ai_context_assembler import AiContextAssembler


CapabilityRunner = Callable[[dict[str, Any]], dict[str, Any]]


class AiCopilotService:
    def __init__(
        self,
        session: Session,
        *,
        context_assembler: AiContextAssembler | None = None,
        artifact_service: AiArtifactService | None = None,
        capability_runners: dict[str, CapabilityRunner] | None = None,
    ) -> None:
        self._context_assembler = context_assembler or AiContextAssembler(session)
        self._artifact_service = artifact_service or AiArtifactService(session)
        self._capability_runners = capability_runners or {}

    def preview(
        self,
        *,
        capability: AiArtifactCapability,
        target_type: AiArtifactTargetType,
        target_id: int,
        project_id: int | None = None,
        suite_id: int | None = None,
        case_id: int | None = None,
        execution_id: int | None = None,
        report_id: int | None = None,
        provider: str = "",
        model: str = "",
        created_by_user_id: int | None = None,
        supplemental_input: dict[str, Any] | None = None,
    ) -> AiCopilotPreviewResponse:
        runner = self._capability_runners.get(capability.value)
        if runner is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported AI capability: {capability.value}",
            )

        context = self._context_assembler.build_context(
            capability=capability.value,
            target_type=target_type.value,
            target_id=target_id,
        )
        if supplemental_input:
            context = {**context, **dict(supplemental_input)}
        generated = runner(context)
        result = generated.get("result") if isinstance(generated.get("result"), dict) else {}
        warnings = [str(item) for item in generated.get("warnings") or []]
        call_trace = self._normalize_call_trace(generated.get("call_trace"))

        artifact = self._artifact_service.create_draft_artifact(
            capability=capability,
            target_type=target_type,
            target_id=target_id,
            project_id=project_id,
            suite_id=suite_id,
            case_id=case_id,
            execution_id=execution_id,
            report_id=report_id,
            input_json=context,
            output_json=result,
            warnings=warnings,
            provider=provider,
            model=model,
            created_by_user_id=created_by_user_id,
            call_trace=call_trace,
        )
        return AiCopilotPreviewResponse(
            artifact_id=artifact.artifact_id,
            capability=capability,
            status=AiArtifactStatus.draft,
            warnings=warnings,
            result=result,
            call_trace=call_trace,
        )

    def list_history(
        self,
        *,
        capability: AiArtifactCapability,
        target_type: AiArtifactTargetType,
        target_id: int,
    ) -> AiArtifactHistoryListRead:
        artifacts = self._artifact_service.list_history(
            capability=capability,
            target_type=target_type,
            target_id=target_id,
        )
        return AiArtifactHistoryListRead(items=[AiArtifactRead.model_validate(item) for item in artifacts])

    def _normalize_call_trace(self, raw_call_trace: Any) -> AiCallTraceRead:
        if isinstance(raw_call_trace, AiCallTraceRead):
            return raw_call_trace
        if isinstance(raw_call_trace, dict):
            return AiCallTraceRead.model_validate(raw_call_trace)
        return AiCallTraceRead(call_mode="deterministic", trace_json={})
