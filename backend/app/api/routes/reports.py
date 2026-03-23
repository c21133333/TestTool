from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import require_authenticated_user
from backend.app.core.database import session_scope
from backend.app.core.responses import ApiResponse
from backend.app.models.user import User
from backend.app.schemas.report import ReportRead
from backend.app.services.report_service import ReportService

router = APIRouter()


@router.get("", response_model=ApiResponse[list[ReportRead]])
def list_reports(
    _: User = Depends(require_authenticated_user),
    session: Session = Depends(session_scope),
) -> ApiResponse[list[ReportRead]]:
    reports = ReportService(session).list_reports()
    return ApiResponse.ok(data=[ReportRead.model_validate(report) for report in reports], message="Reports loaded.")


@router.get("/{report_id}/content", include_in_schema=False)
def get_report_content(
    report_id: int,
    _: User = Depends(require_authenticated_user),
    session: Session = Depends(session_scope),
) -> FileResponse:
    report = ReportService(session).get_report(report_id)
    file_path = Path(report.file_path)
    media_type = "text/html" if report.report_type == "html" else "application/json"
    return FileResponse(file_path, media_type=media_type, filename=file_path.name)
