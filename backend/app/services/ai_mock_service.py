from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.schemas.ai_copilot import AiArtifactStatus, AiMockResult
from backend.app.services.ai_artifact_service import AiArtifactService
from backend.app.services.ai_mock_llm_service import AiMockLlmService
from backend.app.services.ai_mock_template_seed_service import AiMockTemplateSeedService
from backend.app.services.workspace_service import WorkspaceService


class AiMockService:
    def __init__(
        self,
        session: Session | None = None,
        *,
        llm_service: AiMockLlmService | None = None,
    ) -> None:
        self._session = session
        self._seed_service = AiMockTemplateSeedService()
        self._llm_service = llm_service or AiMockLlmService()

    def generate_preview(self, context: dict[str, Any]) -> dict[str, Any]:
        snapshot = context.get("input_snapshot") if isinstance(context.get("input_snapshot"), dict) else {}
        baseline_result = self._seed_service.build_result(snapshot)
        baseline_templates = [item.model_dump() for item in baseline_result.mock_templates]
        has_rule_baseline = bool(baseline_templates)

        baseline_warnings: list[str] = ["当前 AI Mock 仍以导出模板为主，不会直接启用 runtime mock。"]
        if not has_rule_baseline:
            baseline_warnings.append("当前 case 上下文不足，规则基线未能稳定推导出 Mock 模板。")

        runtime = self._llm_service.resolve_runtime()
        llm_templates, llm_warnings = self._llm_service.analyze_templates(
            runtime=runtime,
            input_snapshot=snapshot,
            baseline_templates=baseline_templates,
            has_rule_baseline=has_rule_baseline,
        )
        merged_templates = self._merge_templates(baseline_templates=baseline_templates, llm_templates=llm_templates)
        if not has_rule_baseline:
            merged_templates = [self._downgrade_to_draft_template(item) for item in merged_templates]

        warnings = self._merge_warnings(
            baseline_warnings=baseline_warnings,
            llm_warnings=llm_warnings,
            has_rule_baseline=has_rule_baseline,
            draft_warning="以下 Mock 建议未基于规则保底生成，可信度较低，请人工确认后再应用。",
        )
        if not merged_templates and not warnings:
            warnings = ["当前未能生成可直接应用的 Mock 模板，请补充响应样本或先执行一次用例后再试。"]

        return {
            "result": AiMockResult.model_validate({"mock_templates": merged_templates}).model_dump(),
            "warnings": warnings,
            "call_trace": self._llm_service.last_call_trace,
        }

    def apply_artifact(
        self,
        artifact_id: str,
        *,
        selected_template_ids: list[str],
        override_existing: bool = False,
    ):
        if self._session is None:
            raise RuntimeError("AiMockService.apply_artifact requires a database session.")
        if not selected_template_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="应用前至少选择一个 Mock 模板。",
            )

        artifact_service = AiArtifactService(self._session)
        artifact = artifact_service.accept_artifact(artifact_id)
        if artifact.capability != "mock":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI 产物能力类型不匹配。")
        if artifact.case_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI 产物没有绑定到用例。")

        available_templates = [
            item for item in (artifact.output_json or {}).get("mock_templates", []) if isinstance(item, dict)
        ]
        selected_lookup = {str(item.get("template_id")): item for item in available_templates if item.get("template_id")}
        selected_templates = [selected_lookup[template_id] for template_id in selected_template_ids if template_id in selected_lookup]
        if not selected_templates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="所选 Mock 模板不存在于当前 AI 产物中。",
            )

        saved_case = WorkspaceService(self._session).save_ai_mock_templates(
            artifact.case_id,
            selected_templates,
            override_existing=override_existing,
        )
        artifact.status = AiArtifactStatus.applied.value
        artifact_service.save(artifact)
        return saved_case

    def export_artifact(self, artifact_id: str) -> dict[str, Any]:
        if self._session is None:
            raise RuntimeError("AiMockService.export_artifact requires a database session.")

        artifact = AiArtifactService(self._session).get_artifact_or_404(artifact_id)
        if artifact.capability != "mock":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI 产物能力类型不匹配。")
        if artifact.case_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI 产物没有绑定到用例。")

        return {
            "artifact_id": artifact.artifact_id,
            "capability": artifact.capability,
            "case_id": artifact.case_id,
            "status": artifact.status,
            "warnings": list(artifact.warnings_json or []),
            "mock_templates": [
                item for item in (artifact.output_json or {}).get("mock_templates", []) if isinstance(item, dict)
            ],
        }

    def _merge_templates(
        self,
        *,
        baseline_templates: list[dict[str, Any]],
        llm_templates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged_by_key: dict[str, dict[str, Any]] = {}
        ordered_keys: list[str] = []

        for item in baseline_templates:
            normalized = self._normalize_template(item)
            if normalized is None:
                continue
            key = self._template_key(normalized)
            merged_by_key[key] = normalized
            ordered_keys.append(key)

        for item in llm_templates:
            normalized = self._normalize_template(item)
            if normalized is None:
                continue
            key = self._template_key(normalized)
            if key not in merged_by_key:
                ordered_keys.append(key)
            merged_by_key[key] = normalized

        return [merged_by_key[key] for key in ordered_keys[:4]]

    def _normalize_template(self, item: dict[str, Any]) -> dict[str, Any] | None:
        template_id = str(item.get("template_id") or "").strip()
        scenario_name = str(item.get("scenario_name") or "").strip()
        response_template = item.get("response_template")
        mock_rules = item.get("mock_rules")
        try:
            status_code = int(item.get("status_code"))
        except (TypeError, ValueError):
            return None
        if not template_id or not scenario_name or not isinstance(response_template, dict) or not isinstance(mock_rules, list):
            return None
        normalized_rules = [rule for rule in mock_rules if isinstance(rule, dict) and rule.get("method") and rule.get("path")]
        if not normalized_rules:
            return None
        return {
            "template_id": template_id,
            "scenario_name": scenario_name,
            "status_code": status_code,
            "response_template": response_template,
            "mock_rules": normalized_rules,
            "reason": str(item.get("reason") or "建议补充该 Mock 模板以增强执行前准备。"),
            "confidence": self._normalize_confidence(item.get("confidence"), fallback=0.84),
        }

    def _template_key(self, item: dict[str, Any]) -> str:
        first_rule = item.get("mock_rules")[0] if item.get("mock_rules") else {}
        return "|".join(
            [
                str(item.get("template_id") or ""),
                str(item.get("scenario_name") or ""),
                str(first_rule.get("method") or ""),
                str(first_rule.get("path") or ""),
                str(item.get("status_code") or ""),
            ]
        )

    def _merge_warnings(
        self,
        *,
        baseline_warnings: list[str],
        llm_warnings: list[str],
        has_rule_baseline: bool,
        draft_warning: str,
    ) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()

        def _append(items: list[str]) -> None:
            for item in items:
                normalized = str(item).strip()
                if not normalized or normalized in seen:
                    continue
                ordered.append(normalized)
                seen.add(normalized)

        _append(baseline_warnings)
        _append(llm_warnings)
        if not has_rule_baseline:
            _append([draft_warning])
        return ordered

    def _downgrade_to_draft_template(self, item: dict[str, Any]) -> dict[str, Any]:
        draft_item = dict(item)
        draft_item["confidence"] = min(self._normalize_confidence(draft_item.get("confidence"), fallback=0.64), 0.64)
        reason = str(draft_item.get("reason") or "").strip()
        if reason and "草案" not in reason:
            draft_item["reason"] = f"{reason} 当前缺少规则保底，此模板为低可信度草案。"
        elif not reason:
            draft_item["reason"] = "当前缺少规则保底，此模板为基于上下文推断的低可信度草案。"
        return draft_item

    def _normalize_confidence(self, value: Any, *, fallback: float) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return fallback
        return max(0.0, min(1.0, confidence))
