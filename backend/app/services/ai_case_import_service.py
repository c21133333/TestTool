from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.observability import get_logger, log_event
from backend.app.schemas.ai_case_draft import (
    AiCaseDraftImportFailure,
    AiCaseDraftImportRequest,
    AiCaseDraftImportResult,
    AiCaseDraftPayload,
)
from backend.app.schemas.workspace import ApiCaseCreate, SuiteCreate
from backend.app.services.workspace_service import WorkspaceService

logger = get_logger("ai_case")

_KNOWN_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}


class AiCaseImportService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._workspace = WorkspaceService(session)

    def import_drafts(self, payload: AiCaseDraftImportRequest) -> AiCaseDraftImportResult:
        self._workspace.get_project(payload.project_id)
        selected_rows = [draft for draft in payload.drafts if draft.selected]
        if not selected_rows:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select at least one draft to import.")

        log_event(logger, "ai_case.import.started", project_id=payload.project_id, suite_name=payload.suite_name, selected_count=len(selected_rows))
        suite = self._workspace.create_suite(
            SuiteCreate(project_id=payload.project_id, name=payload.suite_name, description="Imported from AI-generated Markdown drafts.")
        )

        created_cases = 0
        failures: list[AiCaseDraftImportFailure] = []
        for row in selected_rows:
            try:
                normalized_case = self._normalize_payload(row.case)
                self._workspace.create_case(self._build_case_payload(suite_id=suite.id, case_payload=normalized_case, row=row))
                created_cases += 1
            except Exception as exc:  # noqa: BLE001
                failures.append(AiCaseDraftImportFailure(draft_id=row.draft_id, reason=str(exc)))

        skipped_cases = len(selected_rows) - created_cases
        log_event(
            logger,
            "ai_case.import.completed",
            level=logging.WARNING if failures else logging.INFO,
            project_id=payload.project_id,
            suite_id=suite.id,
            suite_name=suite.name,
            created_cases=created_cases,
            skipped_cases=skipped_cases,
            failure_count=len(failures),
        )
        return AiCaseDraftImportResult(
            suite_id=suite.id,
            suite_name=suite.name,
            created_cases=created_cases,
            skipped_cases=skipped_cases,
            failures=failures,
        )

    def _normalize_payload(self, payload: dict[str, Any]) -> AiCaseDraftPayload:
        case_payload = AiCaseDraftPayload.model_validate(payload)
        errors = self._validate_case_payload(case_payload)
        if errors:
            raise ValueError("; ".join(errors))
        return case_payload

    def _validate_case_payload(self, payload: AiCaseDraftPayload) -> list[str]:
        errors: list[str] = []
        if not payload.name:
            errors.append("Case name is required.")
        if not payload.url:
            errors.append("URL is required.")
        if payload.method not in _KNOWN_HTTP_METHODS:
            errors.append(f"Unsupported HTTP method: {payload.method}.")
        return errors

    def _build_case_payload(self, *, suite_id: int, case_payload: AiCaseDraftPayload, row: Any) -> ApiCaseCreate:
        metadata = dict(case_payload.metadata_json)
        metadata.setdefault("ai_generated", True)
        metadata.setdefault("source_type", "markdown_ai")
        metadata["source_excerpt"] = row.source_excerpt
        metadata["source_location"] = row.source_location
        metadata["draft_id"] = row.draft_id
        return ApiCaseCreate(
            suite_id=suite_id,
            name=case_payload.name,
            method=case_payload.method,
            url=case_payload.url,
            description=case_payload.description,
            headers_json=case_payload.headers_json,
            body_json=case_payload.body_json,
            assertions_json=case_payload.assertions_json,
            pre_processors_json=[],
            post_processors_json=[],
            metadata_json=metadata,
        )
