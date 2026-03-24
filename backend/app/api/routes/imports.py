from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from backend.app.api.dependencies.auth import require_authenticated_user, require_roles
from backend.app.core.database import session_scope
from backend.app.core.responses import ApiResponse
from backend.app.models.user import User
from backend.app.models.user import UserRole
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.compatibility_service import CompatibilityService
from backend.app.services.import_service import ImportService

router = APIRouter()


@router.get("/policy", response_model=ApiResponse[dict])
def get_import_policy(current_user: User = Depends(require_authenticated_user)) -> ApiResponse[dict]:
    del current_user
    policy = CompatibilityService().get_legacy_policy()
    return ApiResponse.ok(data=policy, message="Legacy compatibility policy loaded.")


@router.post("/excel", response_model=ApiResponse[dict])
def import_excel(
    project_id: int = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[dict]:
    CompatibilityService().ensure_legacy_imports_available()
    suffix = Path(file.filename or "import.xlsx").suffix or ".xlsx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(file.file.read())
        temp_path = handle.name
    try:
        result = ImportService(session).import_excel(project_id, temp_path)
    finally:
        Path(temp_path).unlink(missing_ok=True)
    AuditLogService(session).record(
        actor=current_user,
        action="import.excel",
        resource_type="project",
        resource_id=project_id,
        summary=f"Imported Excel into project #{project_id}",
        details={"project_id": project_id, "file_name": file.filename or "import.xlsx", **result},
    )
    return ApiResponse.ok(data=result, message="Excel imported.")


@router.post("/legacy-project", response_model=ApiResponse[dict])
def import_legacy_project(
    project_id: int = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.tester)),
    session: Session = Depends(session_scope),
) -> ApiResponse[dict]:
    CompatibilityService().ensure_legacy_imports_available()
    suffix = Path(file.filename or "project.json").suffix or ".json"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(file.file.read())
        temp_path = handle.name
    try:
        result = ImportService(session).import_legacy_project(project_id, temp_path)
    finally:
        Path(temp_path).unlink(missing_ok=True)
    AuditLogService(session).record(
        actor=current_user,
        action="import.legacy_project",
        resource_type="project",
        resource_id=project_id,
        summary=f"Imported desktop project.json into project #{project_id}",
        details={"project_id": project_id, "file_name": file.filename or "project.json", **result},
    )
    return ApiResponse.ok(data=result, message="Desktop project imported.")
