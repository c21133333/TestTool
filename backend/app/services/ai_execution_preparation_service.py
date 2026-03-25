from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.schemas.execution import AiExecutionPreparationRead, AiExecutionPreparationSelection
from backend.app.services.workspace_service import WorkspaceService


class AiExecutionPreparationService:
    def __init__(self, session: Session) -> None:
        self._workspace = WorkspaceService(session)

    def build_case_preparation(
        self,
        *,
        case_id: int,
        selection: AiExecutionPreparationSelection | None = None,
    ) -> AiExecutionPreparationRead:
        api_case = self._workspace.get_case(case_id)
        normalized_selection = selection or AiExecutionPreparationSelection()
        selected_variants = self._resolve_selected_items(
            available_items=self._workspace.list_ai_test_data_variants(case_id),
            selected_ids=normalized_selection.selected_test_data_variant_ids,
            identity_key="variant_id",
            missing_message="Selected AI test data variant was not found in case metadata.",
        )
        selected_templates = self._resolve_selected_items(
            available_items=self._workspace.list_ai_mock_templates(case_id),
            selected_ids=normalized_selection.selected_mock_template_ids,
            identity_key="template_id",
            missing_message="Selected AI mock template was not found in case metadata.",
        )
        request_body = self._apply_variants(api_case.body_json, selected_variants)
        return AiExecutionPreparationRead(
            case_id=case_id,
            request_body=request_body,
            selected_test_data_variants=selected_variants,
            selected_mock_templates=selected_templates,
            summary={
                "selected_variant_ids": [str(item.get("variant_id") or "") for item in selected_variants],
                "selected_template_ids": [str(item.get("template_id") or "") for item in selected_templates],
                "selected_variant_count": len(selected_variants),
                "selected_template_count": len(selected_templates),
            },
        )

    def _resolve_selected_items(
        self,
        *,
        available_items: list[dict[str, Any]],
        selected_ids: list[str],
        identity_key: str,
        missing_message: str,
    ) -> list[dict[str, Any]]:
        normalized_ids = [str(item).strip() for item in selected_ids if str(item).strip()]
        if not normalized_ids:
            return []

        items_by_id = {str(item.get(identity_key) or "").strip(): dict(item) for item in available_items if isinstance(item, dict)}
        resolved_items: list[dict[str, Any]] = []
        for selected_id in normalized_ids:
            resolved = items_by_id.get(selected_id)
            if resolved is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=missing_message)
            resolved_items.append(resolved)
        return resolved_items

    def _apply_variants(self, baseline_body: Any, selected_variants: list[dict[str, Any]]) -> Any:
        result = deepcopy(baseline_body)
        for variant in selected_variants:
            payload_patch = variant.get("payload_patch")
            if not isinstance(payload_patch, dict):
                continue
            if not isinstance(result, dict):
                result = deepcopy(payload_patch)
                continue
            result = self._deep_merge_dict(result, payload_patch)
        return result

    def _deep_merge_dict(self, baseline: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        merged = deepcopy(baseline)
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._deep_merge_dict(merged[key], value)
            else:
                merged[key] = deepcopy(value)
        return merged
