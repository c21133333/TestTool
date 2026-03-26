from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import require_roles
from backend.app.core.database import session_scope
from backend.app.core.responses import ApiResponse
from backend.app.models.user import User, UserRole
from backend.app.schemas.ai_case_draft import AiCaseDraftBatchRead
from backend.app.schemas.ai_copilot import (
    AiArtifactCapability,
    AiArtifactHistoryListRead,
    AiArtifactLineageRead,
    AiChatSessionListRead,
    AiChatSessionRead,
    AiArtifactTargetType,
    AiAssertionApplyRequest,
    AiAssertionPreviewRequest,
    AiChatStreamRequest,
    AiCopilotPreviewResponse,
    AiCoverageScanRequest,
    AiDiagnosisPreviewRequest,
    AiMockApplyRequest,
    AiMockPreviewRequest,
    AiReportSummaryApplyRequest,
    AiReportSummaryPreviewRequest,
    AiTestDataApplyRequest,
    AiTestDataPreviewRequest,
    AiTestPointGenerateDraftsRequest,
    AiTestPointPreviewRequest,
)
from backend.app.schemas.workspace import ApiCaseRead
from backend.app.services.ai_copilot_service import AiCopilotService
from backend.app.services.ai_assertion_service import AiAssertionService
from backend.app.services.ai_artifact_lineage_service import AiArtifactLineageService
from backend.app.services.ai_chat_context_service import AiChatContextService
from backend.app.services.ai_chat_history_service import AiChatHistoryService
from backend.app.services.ai_chat_service import AiChatService
from backend.app.services.ai_coverage_service import AiCoverageService
from backend.app.services.ai_diagnosis_service import AiDiagnosisService
from backend.app.services.ai_mock_service import AiMockService
from backend.app.services.ai_report_summary_service import AiReportSummaryService
from backend.app.services.ai_test_data_service import AiTestDataService
from backend.app.services.ai_test_point_draft_service import AiTestPointDraftService
from backend.app.services.ai_test_point_service import AiTestPointService
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.report_service import ReportService
from backend.app.services.workspace_service import WorkspaceService

router = APIRouter()


def _trace_details(result: AiCopilotPreviewResponse) -> dict[str, object]:
    if result.call_trace is None:
        return {"call_mode": "deterministic", "failure_category": ""}
    return {
        "call_mode": result.call_trace.call_mode,
        "failure_category": result.call_trace.failure_category,
    }


@router.post("/chat/stream")
def stream_chat(
    payload: AiChatStreamRequest,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester, UserRole.developer)),
    session: Session = Depends(session_scope),
) -> StreamingResponse:
    stream = AiChatService(
        context_service=AiChatContextService(session),
        history_service=AiChatHistoryService(session),
    ).stream_reply(
        user_id=current_user.id,
        session_id=payload.session_id,
        chat_mode=payload.chat_mode,
        project_id=payload.project_id,
        page_path=payload.page_path,
        page_title=payload.page_title,
        messages=payload.messages,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

def _build_chat_session_summary(chat_session) -> dict[str, object]:
    return {
        "session_id": chat_session.id,
        "title": chat_session.title,
        "chat_mode": chat_session.chat_mode,
        "project_id": chat_session.project_id,
        "project_name": chat_session.project.name if chat_session.project is not None else None,
        "latest_message_preview": chat_session.latest_message_preview,
        "message_count": chat_session.message_count,
        "updated_at": chat_session.updated_at.isoformat(),
    }


def _build_chat_session_detail(chat_session) -> AiChatSessionRead:
    return AiChatSessionRead.model_validate(
        {
            **_build_chat_session_summary(chat_session),
            "page_path": chat_session.page_path,
            "page_title": chat_session.page_title,
            "messages": [
                {
                    "message_id": message.id,
                    "role": message.role,
                    "content": message.content,
                    "created_at": message.created_at.isoformat(),
                }
                for message in sorted(chat_session.messages, key=lambda current: (current.order_index, current.id))
            ],
        }
    )


@router.get("/chat/sessions", response_model=ApiResponse[AiChatSessionListRead])
def list_chat_sessions(
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester, UserRole.developer)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiChatSessionListRead]:
    sessions = AiChatHistoryService(session).list_sessions_for_user(current_user.id)
    return ApiResponse.ok(
        data=AiChatSessionListRead(
            items=[
                _build_chat_session_summary(chat_session)
                for chat_session in sessions
            ]
        ),
        message="AI chat sessions loaded.",
    )


@router.get("/chat/sessions/{session_id}", response_model=ApiResponse[AiChatSessionRead])
def get_chat_session(
    session_id: int,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester, UserRole.developer)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiChatSessionRead]:
    chat_session = AiChatHistoryService(session).get_session_for_user(session_id, current_user.id)
    return ApiResponse.ok(data=_build_chat_session_detail(chat_session), message="AI chat session loaded.")


@router.delete("/chat/sessions/{session_id}", response_model=ApiResponse[None])
def delete_chat_session(
    session_id: int,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester, UserRole.developer)),
    session: Session = Depends(session_scope),
) -> ApiResponse[None]:
    history_service = AiChatHistoryService(session)
    chat_session = history_service.get_session_for_user(session_id, current_user.id)
    AuditLogService(session).record(
        actor=current_user,
        action="ai_chat.delete",
        resource_type="ai_chat_session",
        resource_id=chat_session.id,
        summary=f"Deleted AI chat session #{chat_session.id}",
        details={
            "session_id": chat_session.id,
            "chat_mode": chat_session.chat_mode,
            "project_id": chat_session.project_id,
            "message_count": chat_session.message_count,
            "title": chat_session.title,
        },
    )
    history_service.delete_session_for_user(session_id, current_user.id)
    return ApiResponse.ok(message="AI chat session deleted.")


@router.get("/artifacts/{artifact_id}/lineage", response_model=ApiResponse[AiArtifactLineageRead])
def artifact_lineage(
    artifact_id: str,
    _: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiArtifactLineageRead]:
    result = AiArtifactLineageService(session).get_lineage(artifact_id)
    return ApiResponse.ok(data=result, message="AI artifact lineage loaded.")


def _build_copilot_service(session: Session) -> AiCopilotService:
    return AiCopilotService(
        session,
        capability_runners={
            AiArtifactCapability.assertion.value: AiAssertionService().generate_preview,
            AiArtifactCapability.coverage.value: AiCoverageService(session).generate_preview,
            AiArtifactCapability.diagnosis.value: AiDiagnosisService().generate_preview,
            AiArtifactCapability.mock.value: AiMockService(session).generate_preview,
            AiArtifactCapability.report_summary.value: AiReportSummaryService().generate_preview,
            AiArtifactCapability.test_data.value: AiTestDataService(session).generate_preview,
            AiArtifactCapability.test_point.value: AiTestPointService(session).generate_preview,
        },
    )


def _resolve_coverage_target(
    payload: AiCoverageScanRequest,
    workspace_service: WorkspaceService,
) -> tuple[AiArtifactTargetType, int, int, int | None]:
    if payload.project_id and payload.suite_id:
        raise ValueError("Provide either project_id or suite_id for coverage scan, not both.")
    if payload.suite_id:
        suite = workspace_service.get_suite(payload.suite_id)
        return AiArtifactTargetType.suite, suite.id, suite.project_id, suite.id
    if payload.project_id:
        project = workspace_service.get_project(payload.project_id)
        return AiArtifactTargetType.project, project.id, project.id, None
    raise ValueError("project_id or suite_id is required for coverage scan.")


def _resolve_test_point_target(
    payload: AiTestPointPreviewRequest,
    workspace_service: WorkspaceService,
) -> tuple[AiArtifactTargetType, int, int, int | None]:
    if payload.project_id and payload.suite_id:
        raise ValueError("Provide either project_id or suite_id for test point preview, not both.")
    if payload.suite_id:
        suite = workspace_service.get_suite(payload.suite_id)
        return AiArtifactTargetType.suite, suite.id, suite.project_id, suite.id
    if payload.project_id:
        project = workspace_service.get_project(payload.project_id)
        return AiArtifactTargetType.project, project.id, project.id, None
    raise ValueError("project_id or suite_id is required for test point preview.")


@router.post("/diagnosis/preview", response_model=ApiResponse[AiCopilotPreviewResponse])
def preview_diagnosis(
    payload: AiDiagnosisPreviewRequest,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiCopilotPreviewResponse]:
    result = _build_copilot_service(session).preview(
        capability=AiArtifactCapability.diagnosis,
        target_type=AiArtifactTargetType.execution,
        target_id=payload.execution_id,
        execution_id=payload.execution_id,
        created_by_user_id=current_user.id,
    )
    AuditLogService(session).record(
        actor=current_user,
        action="ai_copilot.diagnosis.preview",
        resource_type="execution",
        resource_id=payload.execution_id,
        summary=f"Generated AI diagnosis for execution #{payload.execution_id}",
        details={"execution_id": payload.execution_id, "artifact_id": result.artifact_id, **_trace_details(result)},
    )
    return ApiResponse.ok(data=result, message="AI diagnosis generated.")


@router.get("/diagnosis/history", response_model=ApiResponse[AiArtifactHistoryListRead])
def diagnosis_history(
    execution_id: int = Query(..., ge=1),
    _: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiArtifactHistoryListRead]:
    result = _build_copilot_service(session).list_history(
        capability=AiArtifactCapability.diagnosis,
        target_type=AiArtifactTargetType.execution,
        target_id=execution_id,
    )
    return ApiResponse.ok(data=result, message="AI diagnosis history loaded.")


@router.post("/coverage/scan", response_model=ApiResponse[AiCopilotPreviewResponse])
def scan_coverage(
    payload: AiCoverageScanRequest,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiCopilotPreviewResponse]:
    workspace = WorkspaceService(session)
    try:
        target_type, target_id, project_id, suite_id = _resolve_coverage_target(payload, workspace)
    except ValueError as exc:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    result = _build_copilot_service(session).preview(
        capability=AiArtifactCapability.coverage,
        target_type=target_type,
        target_id=target_id,
        project_id=project_id,
        suite_id=suite_id,
        created_by_user_id=current_user.id,
    )
    AuditLogService(session).record(
        actor=current_user,
        action="ai_copilot.coverage.scan",
        resource_type=target_type.value,
        resource_id=target_id,
        summary=f"Scanned AI coverage for {target_type.value} #{target_id}",
        details={"target_type": target_type.value, "target_id": target_id, "artifact_id": result.artifact_id, **_trace_details(result)},
    )
    return ApiResponse.ok(data=result, message="AI coverage scan generated.")


@router.get("/coverage/history", response_model=ApiResponse[AiArtifactHistoryListRead])
def coverage_history(
    target_type: AiArtifactTargetType = Query(...),
    target_id: int = Query(..., ge=1),
    _: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiArtifactHistoryListRead]:
    if target_type not in {AiArtifactTargetType.project, AiArtifactTargetType.suite}:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Coverage history supports project or suite target only.")
    result = _build_copilot_service(session).list_history(
        capability=AiArtifactCapability.coverage,
        target_type=target_type,
        target_id=target_id,
    )
    return ApiResponse.ok(data=result, message="AI coverage history loaded.")


@router.post("/test-points/preview", response_model=ApiResponse[AiCopilotPreviewResponse])
def preview_test_points(
    payload: AiTestPointPreviewRequest,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiCopilotPreviewResponse]:
    workspace = WorkspaceService(session)
    try:
        target_type, target_id, project_id, suite_id = _resolve_test_point_target(payload, workspace)
    except ValueError as exc:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    result = _build_copilot_service(session).preview(
        capability=AiArtifactCapability.test_point,
        target_type=target_type,
        target_id=target_id,
        project_id=project_id,
        suite_id=suite_id,
        created_by_user_id=current_user.id,
        supplemental_input={
            "enable_llm": True,
            "markdown_text": payload.markdown_text,
            "prompt_hints": payload.prompt_hints,
            "coverage_missing_dimensions": [item.model_dump() for item in payload.coverage_missing_dimensions],
        },
    )
    AuditLogService(session).record(
        actor=current_user,
        action="ai_copilot.test_point.preview",
        resource_type=target_type.value,
        resource_id=target_id,
        summary=f"Generated AI test points for {target_type.value} #{target_id}",
        details={"target_type": target_type.value, "target_id": target_id, "artifact_id": result.artifact_id, **_trace_details(result)},
    )
    return ApiResponse.ok(data=result, message="AI test points generated.")


@router.get("/test-points/history", response_model=ApiResponse[AiArtifactHistoryListRead])
def test_point_history(
    target_type: AiArtifactTargetType = Query(...),
    target_id: int = Query(..., ge=1),
    _: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiArtifactHistoryListRead]:
    if target_type not in {AiArtifactTargetType.project, AiArtifactTargetType.suite}:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Test point history supports project or suite target only.")
    result = _build_copilot_service(session).list_history(
        capability=AiArtifactCapability.test_point,
        target_type=target_type,
        target_id=target_id,
    )
    return ApiResponse.ok(data=result, message="AI test point history loaded.")


@router.post("/test-points/generate-drafts", response_model=ApiResponse[AiCaseDraftBatchRead])
def generate_test_point_drafts(
    payload: AiTestPointGenerateDraftsRequest,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiCaseDraftBatchRead]:
    result = AiTestPointDraftService(session).generate_drafts_from_artifact(
        artifact_id=payload.artifact_id,
        selected_point_ids=payload.selected_point_ids,
        project_id=payload.project_id,
        suite_name=payload.suite_name,
        provider=payload.provider,
        model=payload.model,
        base_url=payload.base_url,
        api_key=payload.api_key,
        timeout_seconds=payload.timeout_seconds,
    )
    AuditLogService(session).record(
        actor=current_user,
        action="ai_copilot.test_point.generate_drafts",
        resource_type="project",
        resource_id=payload.project_id,
        summary=f"Generated AI case drafts from test points for project #{payload.project_id}",
        details={
            "project_id": payload.project_id,
            "suite_name": payload.suite_name,
            "artifact_id": payload.artifact_id,
            "selected_point_count": len(payload.selected_point_ids),
            "draft_count": len(result.drafts),
            "history_id": result.history_id,
        },
    )
    return ApiResponse.ok(data=result, message="AI case drafts generated from test points.")


@router.post("/assertions/preview", response_model=ApiResponse[AiCopilotPreviewResponse])
def preview_assertions(
    payload: AiAssertionPreviewRequest,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiCopilotPreviewResponse]:
    case = WorkspaceService(session).get_case(payload.case_id)
    result = _build_copilot_service(session).preview(
        capability=AiArtifactCapability.assertion,
        target_type=AiArtifactTargetType.case,
        target_id=payload.case_id,
        project_id=case.suite.project_id,
        suite_id=case.suite_id,
        case_id=case.id,
        created_by_user_id=current_user.id,
    )
    AuditLogService(session).record(
        actor=current_user,
        action="ai_copilot.assertion.preview",
        resource_type="case",
        resource_id=payload.case_id,
        summary=f"Generated AI assertion suggestions for case #{payload.case_id}",
        details={"case_id": payload.case_id, "artifact_id": result.artifact_id, **_trace_details(result)},
    )
    return ApiResponse.ok(data=result, message="AI assertion suggestions generated.")


@router.post("/assertions/{artifact_id}/apply", response_model=ApiResponse[ApiCaseRead])
def apply_assertions(
    artifact_id: str,
    payload: AiAssertionApplyRequest,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[ApiCaseRead]:
    api_case = AiAssertionService(session).apply_artifact(artifact_id, override_existing=payload.override_existing)
    AuditLogService(session).record(
        actor=current_user,
        action="ai_copilot.assertion.apply",
        resource_type="case",
        resource_id=api_case.id,
        summary=f"Applied AI assertion suggestions to case #{api_case.id}",
        details={"case_id": api_case.id, "artifact_id": artifact_id, "override_existing": payload.override_existing},
    )
    return ApiResponse.ok(data=ApiCaseRead.model_validate(api_case), message="AI assertion suggestions applied.")


@router.post("/test-data/preview", response_model=ApiResponse[AiCopilotPreviewResponse])
def preview_test_data(
    payload: AiTestDataPreviewRequest,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiCopilotPreviewResponse]:
    api_case = WorkspaceService(session).get_case(payload.case_id)
    result = _build_copilot_service(session).preview(
        capability=AiArtifactCapability.test_data,
        target_type=AiArtifactTargetType.case,
        target_id=payload.case_id,
        project_id=api_case.suite.project_id,
        suite_id=api_case.suite_id,
        case_id=api_case.id,
        created_by_user_id=current_user.id,
    )
    AuditLogService(session).record(
        actor=current_user,
        action="ai_copilot.test_data.preview",
        resource_type="case",
        resource_id=payload.case_id,
        summary=f"Generated AI test data variants for case #{payload.case_id}",
        details={"case_id": payload.case_id, "artifact_id": result.artifact_id, **_trace_details(result)},
    )
    return ApiResponse.ok(data=result, message="AI test data variants generated.")


@router.get("/test-data/history", response_model=ApiResponse[AiArtifactHistoryListRead])
def test_data_history(
    case_id: int = Query(..., ge=1),
    _: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiArtifactHistoryListRead]:
    result = _build_copilot_service(session).list_history(
        capability=AiArtifactCapability.test_data,
        target_type=AiArtifactTargetType.case,
        target_id=case_id,
    )
    return ApiResponse.ok(data=result, message="AI test data history loaded.")


@router.post("/test-data/{artifact_id}/apply", response_model=ApiResponse[ApiCaseRead])
def apply_test_data(
    artifact_id: str,
    payload: AiTestDataApplyRequest,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[ApiCaseRead]:
    api_case = AiTestDataService(session).apply_artifact(
        artifact_id,
        selected_variant_ids=payload.selected_variant_ids,
        override_existing=payload.override_existing,
    )
    AuditLogService(session).record(
        actor=current_user,
        action="ai_copilot.test_data.apply",
        resource_type="case",
        resource_id=api_case.id,
        summary=f"Applied AI test data variants to case #{api_case.id}",
        details={
            "case_id": api_case.id,
            "artifact_id": artifact_id,
            "selected_variant_ids": payload.selected_variant_ids,
            "override_existing": payload.override_existing,
        },
    )
    return ApiResponse.ok(data=ApiCaseRead.model_validate(api_case), message="AI test data variants applied.")


@router.get("/test-data/{artifact_id}/export")
def export_test_data(
    artifact_id: str,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> Response:
    bundle = AiTestDataService(session).export_artifact(artifact_id)
    AuditLogService(session).record(
        actor=current_user,
        action="ai_copilot.test_data.export",
        resource_type="case",
        resource_id=bundle["case_id"],
        summary=f"Exported AI test data bundle for case #{bundle['case_id']}",
        details={"case_id": bundle["case_id"], "artifact_id": artifact_id},
    )
    return Response(
        content=json.dumps(bundle, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="ai-test-data-{artifact_id}.json"'},
    )


@router.post("/mock/preview", response_model=ApiResponse[AiCopilotPreviewResponse])
def preview_mock(
    payload: AiMockPreviewRequest,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiCopilotPreviewResponse]:
    api_case = WorkspaceService(session).get_case(payload.case_id)
    result = _build_copilot_service(session).preview(
        capability=AiArtifactCapability.mock,
        target_type=AiArtifactTargetType.case,
        target_id=payload.case_id,
        project_id=api_case.suite.project_id,
        suite_id=api_case.suite_id,
        case_id=api_case.id,
        created_by_user_id=current_user.id,
    )
    AuditLogService(session).record(
        actor=current_user,
        action="ai_copilot.mock.preview",
        resource_type="case",
        resource_id=payload.case_id,
        summary=f"Generated AI mock templates for case #{payload.case_id}",
        details={"case_id": payload.case_id, "artifact_id": result.artifact_id, **_trace_details(result)},
    )
    return ApiResponse.ok(data=result, message="AI mock templates generated.")


@router.get("/mock/history", response_model=ApiResponse[AiArtifactHistoryListRead])
def mock_history(
    case_id: int = Query(..., ge=1),
    _: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiArtifactHistoryListRead]:
    result = _build_copilot_service(session).list_history(
        capability=AiArtifactCapability.mock,
        target_type=AiArtifactTargetType.case,
        target_id=case_id,
    )
    return ApiResponse.ok(data=result, message="AI mock history loaded.")


@router.post("/mock/{artifact_id}/apply", response_model=ApiResponse[ApiCaseRead])
def apply_mock(
    artifact_id: str,
    payload: AiMockApplyRequest,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[ApiCaseRead]:
    api_case = AiMockService(session).apply_artifact(
        artifact_id,
        selected_template_ids=payload.selected_template_ids,
        override_existing=payload.override_existing,
    )
    AuditLogService(session).record(
        actor=current_user,
        action="ai_copilot.mock.apply",
        resource_type="case",
        resource_id=api_case.id,
        summary=f"Applied AI mock templates to case #{api_case.id}",
        details={
            "case_id": api_case.id,
            "artifact_id": artifact_id,
            "selected_template_ids": payload.selected_template_ids,
            "override_existing": payload.override_existing,
        },
    )
    return ApiResponse.ok(data=ApiCaseRead.model_validate(api_case), message="AI mock templates applied.")


@router.get("/mock/{artifact_id}/export")
def export_mock(
    artifact_id: str,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> Response:
    bundle = AiMockService(session).export_artifact(artifact_id)
    AuditLogService(session).record(
        actor=current_user,
        action="ai_copilot.mock.export",
        resource_type="case",
        resource_id=bundle["case_id"],
        summary=f"Exported AI mock bundle for case #{bundle['case_id']}",
        details={"case_id": bundle["case_id"], "artifact_id": artifact_id},
    )
    return Response(
        content=json.dumps(bundle, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="ai-mock-{artifact_id}.json"'},
    )


@router.post("/report-summary/preview", response_model=ApiResponse[AiCopilotPreviewResponse])
def preview_report_summary(
    payload: AiReportSummaryPreviewRequest,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiCopilotPreviewResponse]:
    result = _build_copilot_service(session).preview(
        capability=AiArtifactCapability.report_summary,
        target_type=AiArtifactTargetType.report,
        target_id=payload.report_id,
        report_id=payload.report_id,
        created_by_user_id=current_user.id,
    )
    AuditLogService(session).record(
        actor=current_user,
        action="ai_copilot.report_summary.preview",
        resource_type="report",
        resource_id=payload.report_id,
        summary=f"Generated AI report summary for report #{payload.report_id}",
        details={"report_id": payload.report_id, "artifact_id": result.artifact_id, **_trace_details(result)},
    )
    return ApiResponse.ok(data=result, message="AI report summary generated.")


@router.post("/report-summary/{artifact_id}/apply", response_model=ApiResponse[dict])
def apply_report_summary(
    artifact_id: str,
    _: AiReportSummaryApplyRequest,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[dict]:
    report = ReportService(session).apply_ai_summary(artifact_id)
    AuditLogService(session).record(
        actor=current_user,
        action="ai_copilot.report_summary.apply",
        resource_type="report",
        resource_id=report.id,
        summary=f"Applied AI report summary to report #{report.id}",
        details={"report_id": report.id, "artifact_id": artifact_id},
    )
    return ApiResponse.ok(
        data={"report_id": report.id, "ai_summary": report.metadata_json.get("ai_summary")},
        message="AI report summary applied.",
    )
