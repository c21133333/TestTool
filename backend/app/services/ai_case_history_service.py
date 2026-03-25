from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from openpyxl import Workbook
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.timezone import to_beijing_isoformat
from backend.app.models.ai_case_history import AiCaseHistory
from backend.app.repositories.ai_case_history_repository import AiCaseHistoryRepository
from backend.app.schemas.ai_case_draft import (
    AiCaseDraftBatchRead,
    AiCaseDraftHistoryListRead,
    AiCaseDraftHistorySummaryRead,
)


class AiCaseHistoryService:
    def __init__(self, session: Session) -> None:
        self._repository = AiCaseHistoryRepository(session)
        self._export_dir = settings.resolved_report_dir / "ai_case_history_exports"
        self._export_dir.mkdir(parents=True, exist_ok=True)

    def save_batch(
        self,
        *,
        project_id: int,
        suite_name: str,
        provider: str,
        model: str,
        base_url: str,
        prompt_preset: str,
        prompt_hints: str,
        prompt_hints_effective: str,
        markdown_text: str,
        batch: AiCaseDraftBatchRead,
    ) -> AiCaseDraftBatchRead:
        history_id = uuid4().hex
        record = self._repository.create(
            AiCaseHistory(
                history_id=history_id,
                project_id=project_id,
                suite_name=suite_name,
                provider=provider,
                model=model,
                base_url=base_url,
                prompt_preset=prompt_preset,
                prompt_hints=prompt_hints,
                prompt_hints_effective=prompt_hints_effective,
                markdown_text=markdown_text,
                batch_json=batch.model_dump(mode="json"),
            )
        )
        created_at = to_beijing_isoformat(record.created_at)
        return batch.model_copy(update={"history_id": history_id, "created_at": created_at})

    def list_history(self, *, project_id: int | None = None) -> AiCaseDraftHistoryListRead:
        items: list[AiCaseDraftHistorySummaryRead] = []
        for record in self._repository.list_history(project_id=project_id):
            batch = record.batch_json if isinstance(record.batch_json, dict) else {}
            drafts = batch.get("drafts") if isinstance(batch.get("drafts"), list) else []
            warnings = batch.get("warnings") if isinstance(batch.get("warnings"), list) else []
            items.append(
                AiCaseDraftHistorySummaryRead(
                    history_id=record.history_id,
                    created_at=to_beijing_isoformat(record.created_at),
                    project_id=record.project_id,
                    suite_name=record.suite_name,
                    provider=record.provider,
                    model=record.model,
                    prompt_preset=record.prompt_preset,
                    draft_count=len(drafts),
                    warning_count=len(warnings),
                )
            )
        return AiCaseDraftHistoryListRead(items=items)

    def get_history_batch(self, history_id: str) -> tuple[dict[str, Any], AiCaseDraftBatchRead]:
        record = self._get_history_record(history_id)
        batch_data = record.batch_json
        if not isinstance(batch_data, dict):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AI history batch is corrupted.")
        batch = AiCaseDraftBatchRead.model_validate(batch_data)
        payload = self._build_payload(record)
        batch = batch.model_copy(update={"history_id": history_id, "created_at": payload["created_at"]})
        return payload, batch

    def build_excel_export(self, history_id: str) -> Path:
        _, batch = self.get_history_batch(history_id)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "AI Cases"
        headers = [
            "case_id",
            "case_name",
            "endpoint",
            "request_json",
            "expected_http_status",
            "expected_business_code",
            "assertion_points",
            "category",
            "precondition",
        ]
        sheet.append(headers)
        for draft in batch.drafts:
            request_json = {
                "method": draft.case.method,
                "url": draft.case.url,
                "headers": draft.case.headers_json,
                "body": draft.case.body_json,
            }
            expected_http_status = ""
            expected_business_code = ""
            assertion_points = ""
            for assertion in draft.case.assertions_json:
                if not isinstance(assertion, dict):
                    continue
                if assertion.get("type") == "status_code" and expected_http_status == "":
                    expected_http_status = assertion.get("expected", "")
                elif assertion.get("type") == "json_path" and assertion.get("path") == "$.code" and expected_business_code == "":
                    expected_business_code = assertion.get("expected", "")
                elif assertion.get("type") == "response_body" and assertion_points == "":
                    assertion_points = str(assertion.get("expected") or "")
            if not assertion_points and draft.review_warnings:
                assertion_points = " | ".join(draft.review_warnings[:2])

            sheet.append(
                [
                    draft.draft_id,
                    draft.case.name,
                    draft.case.url,
                    json.dumps(request_json, ensure_ascii=False),
                    expected_http_status,
                    expected_business_code,
                    assertion_points,
                    str(draft.case.metadata_json.get("category") or ""),
                    str(draft.case.metadata_json.get("precondition") or ""),
                ]
            )
        export_path = self._export_dir / f"{history_id}.xlsx"
        workbook.save(export_path)
        return export_path

    def _get_history_record(self, history_id: str) -> AiCaseHistory:
        record = self._repository.get_by_history_id(history_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI generation history not found.")
        return record

    def _build_payload(self, record: AiCaseHistory) -> dict[str, Any]:
        payload = {
            "history_id": record.history_id,
            "created_at": to_beijing_isoformat(record.created_at),
            "project_id": record.project_id,
            "suite_name": record.suite_name,
            "provider": record.provider,
            "model": record.model,
            "base_url": record.base_url,
            "prompt_preset": record.prompt_preset,
            "prompt_hints": record.prompt_hints,
            "prompt_hints_effective": record.prompt_hints_effective,
            "markdown_text": record.markdown_text,
            "batch": record.batch_json,
        }
        if not isinstance(payload, dict):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AI history file is corrupted.")
        return payload
