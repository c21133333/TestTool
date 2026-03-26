from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from fastapi import Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import require_roles
from backend.app.core.database import session_scope
from backend.app.core.responses import ApiResponse
from backend.app.models.user import User
from backend.app.models.user import UserRole
from backend.app.schemas.ai_case_draft import (
    AiCaseDraftBatchRead,
    AiCaseDraftHistoryListRead,
    AiCaseDraftImportRequest,
    AiCaseDraftImportResult,
    AiCaseDraftPreviewRequest,
    AiCaseDraftRerunRequest,
)
from backend.app.services.ai_case_draft_service import AiCaseDraftService
from backend.app.services.ai_case_history_service import AiCaseHistoryService
from backend.app.services.ai_case_import_service import AiCaseImportService
from backend.app.services.audit_log_service import AuditLogService

router = APIRouter()


@router.post("/preview", response_model=ApiResponse[AiCaseDraftBatchRead])
def preview_ai_case_drafts(
    payload: AiCaseDraftPreviewRequest,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiCaseDraftBatchRead]:
    result = AiCaseDraftService(session).preview_drafts(payload)
    AuditLogService(session).record(
        actor=current_user,
        action="ai_case.preview",
        resource_type="project",
        resource_id=payload.project_id,
        summary=f"Generated AI case drafts for project #{payload.project_id}",
        details={
            "project_id": payload.project_id,
            "suite_name": payload.suite_name,
            "prompt_preset": payload.prompt_preset or "balanced",
            "provider": payload.provider or "configured_default",
            "model": payload.model or "configured_default",
            "draft_count": len(result.drafts),
            "warning_count": len(result.warnings),
        },
    )
    return ApiResponse.ok(data=result, message="AI case drafts generated.")


@router.get("/history", response_model=ApiResponse[AiCaseDraftHistoryListRead])
def list_ai_case_draft_history(
    project_id: int | None = Query(default=None),
    _: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiCaseDraftHistoryListRead]:
    result = AiCaseHistoryService(session).list_history(project_id=project_id)
    return ApiResponse.ok(data=result, message="AI case history loaded.")


@router.get("/history/{history_id}", response_model=ApiResponse[AiCaseDraftBatchRead])
def get_ai_case_draft_history(
    history_id: str,
    _: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiCaseDraftBatchRead]:
    _, batch = AiCaseHistoryService(session).get_history_batch(history_id)
    return ApiResponse.ok(data=batch, message="AI case history detail loaded.")


@router.post("/history/{history_id}/rerun", response_model=ApiResponse[AiCaseDraftBatchRead])
def rerun_ai_case_draft_history(
    history_id: str,
    payload: AiCaseDraftRerunRequest,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiCaseDraftBatchRead]:
    result = AiCaseDraftService(session).rerun_from_history(history_id, payload)
    AuditLogService(session).record(
        actor=current_user,
        action="ai_case.rerun",
        resource_type="ai_case_history",
        resource_id=history_id,
        summary=f"Re-ran AI case draft generation from history {history_id}",
        details={
            "history_id": history_id,
            "provider": payload.provider or "history_default",
            "model": payload.model or "history_default",
            "draft_count": len(result.drafts),
        },
    )
    return ApiResponse.ok(data=result, message="AI case drafts re-generated from history.")


@router.get("/history/{history_id}/export.xlsx", include_in_schema=False)
def export_ai_case_draft_history_excel(
    history_id: str,
    view: Literal["human", "program", "both"] = Query(default="both"),
    _: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> FileResponse:
    export_path = AiCaseHistoryService(session).build_excel_export(history_id, view=view)
    return FileResponse(
        export_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=export_path.name,
    )


@router.post("/import", response_model=ApiResponse[AiCaseDraftImportResult])
def import_ai_case_drafts(
    payload: AiCaseDraftImportRequest,
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[AiCaseDraftImportResult]:
    result = AiCaseImportService(session).import_drafts(payload)
    AuditLogService(session).record(
        actor=current_user,
        action="ai_case.import",
        resource_type="project",
        resource_id=payload.project_id,
        summary=f"Imported AI case drafts into suite {result.suite_name}",
        details={
            "project_id": payload.project_id,
            "suite_id": result.suite_id,
            "suite_name": result.suite_name,
            "created_cases": result.created_cases,
            "skipped_cases": result.skipped_cases,
            "failure_count": len(result.failures),
        },
    )
    return ApiResponse.ok(data=result, message="AI case drafts imported.")
