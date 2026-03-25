from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.schemas.ai_copilot import AiArtifactStatus, AiTestDataResult
from backend.app.services.ai_artifact_service import AiArtifactService
from backend.app.services.ai_test_data_llm_service import AiTestDataLlmService
from backend.app.services.ai_test_data_seed_service import AiTestDataSeedService
from backend.app.services.workspace_service import WorkspaceService


class AiTestDataService:
    def __init__(
        self,
        session: Session | None = None,
        *,
        llm_service: AiTestDataLlmService | None = None,
    ) -> None:
        self._session = session
        self._seed_service = AiTestDataSeedService()
        self._llm_service = llm_service or AiTestDataLlmService()

    def generate_preview(self, context: dict[str, Any]) -> dict[str, Any]:
        snapshot = context.get("input_snapshot") if isinstance(context.get("input_snapshot"), dict) else {}
        baseline_result = self._seed_service.build_result(snapshot)
        baseline_variants = [item.model_dump() for item in baseline_result.data_variants]
        has_rule_baseline = bool(baseline_variants)

        baseline_warnings: list[str] = []
        if not snapshot.get("recent_success_sample"):
            baseline_warnings.append("没有找到最近一次成功执行样本，测试数据变体将回退为基于已保存请求体推导。")
        if not has_rule_baseline:
            baseline_warnings.append("当前 case 上下文不足，规则基线未能稳定推导出测试数据变体。")

        runtime = self._llm_service.resolve_runtime()
        llm_variants, llm_warnings = self._llm_service.analyze_variants(
            runtime=runtime,
            input_snapshot=snapshot,
            baseline_variants=baseline_variants,
            has_rule_baseline=has_rule_baseline,
        )
        merged_variants = self._merge_variants(baseline_variants=baseline_variants, llm_variants=llm_variants)
        if not has_rule_baseline:
            merged_variants = [self._downgrade_to_draft_variant(item) for item in merged_variants]

        warnings = self._merge_warnings(
            baseline_warnings=baseline_warnings,
            llm_warnings=llm_warnings,
            has_rule_baseline=has_rule_baseline,
            draft_warning="以下测试数据建议未基于规则保底生成，可信度较低，请人工确认后再应用。",
        )
        if not merged_variants and not warnings:
            warnings = ["当前未能生成可直接应用的测试数据建议，请补充请求体或先执行一次用例后再试。"]

        return {
            "result": AiTestDataResult.model_validate({"data_variants": merged_variants}).model_dump(),
            "warnings": warnings,
            "call_trace": self._llm_service.last_call_trace,
        }

    def apply_artifact(
        self,
        artifact_id: str,
        *,
        selected_variant_ids: list[str],
        override_existing: bool = False,
    ):
        if self._session is None:
            raise RuntimeError("AiTestDataService.apply_artifact requires a database session.")
        if not selected_variant_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="应用前至少选择一个测试数据变体。",
            )

        artifact_service = AiArtifactService(self._session)
        artifact = artifact_service.accept_artifact(artifact_id)
        if artifact.capability != "test_data":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI 产物能力类型不匹配。")
        if artifact.case_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI 产物没有绑定到用例。")

        available_variants = [
            item for item in (artifact.output_json or {}).get("data_variants", []) if isinstance(item, dict)
        ]
        selected_lookup = {str(item.get("variant_id")): item for item in available_variants if item.get("variant_id")}
        selected_variants = [selected_lookup[variant_id] for variant_id in selected_variant_ids if variant_id in selected_lookup]
        if not selected_variants:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="所选测试数据变体不存在于当前 AI 产物中。",
            )

        saved_case = WorkspaceService(self._session).save_ai_test_data_variants(
            artifact.case_id,
            selected_variants,
            override_existing=override_existing,
        )
        artifact.status = AiArtifactStatus.applied.value
        artifact_service.save(artifact)
        return saved_case

    def export_artifact(self, artifact_id: str) -> dict[str, Any]:
        if self._session is None:
            raise RuntimeError("AiTestDataService.export_artifact requires a database session.")

        artifact = AiArtifactService(self._session).get_artifact_or_404(artifact_id)
        if artifact.capability != "test_data":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI 产物能力类型不匹配。")
        if artifact.case_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI 产物没有绑定到用例。")

        return {
            "artifact_id": artifact.artifact_id,
            "capability": artifact.capability,
            "case_id": artifact.case_id,
            "status": artifact.status,
            "warnings": list(artifact.warnings_json or []),
            "data_variants": [
                item for item in (artifact.output_json or {}).get("data_variants", []) if isinstance(item, dict)
            ],
        }

    def _merge_variants(
        self,
        *,
        baseline_variants: list[dict[str, Any]],
        llm_variants: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged_by_key: dict[str, dict[str, Any]] = {}
        ordered_keys: list[str] = []

        for item in baseline_variants:
            normalized = self._normalize_variant(item)
            if normalized is None:
                continue
            key = self._variant_key(normalized)
            merged_by_key[key] = normalized
            ordered_keys.append(key)

        for item in llm_variants:
            normalized = self._normalize_variant(item)
            if normalized is None:
                continue
            key = self._variant_key(normalized)
            if key not in merged_by_key:
                ordered_keys.append(key)
            merged_by_key[key] = normalized

        return [merged_by_key[key] for key in ordered_keys[:5]]

    def _normalize_variant(self, item: dict[str, Any]) -> dict[str, Any] | None:
        variant_id = str(item.get("variant_id") or "").strip()
        name = str(item.get("name") or "").strip()
        category = str(item.get("category") or "").strip()
        payload_patch = item.get("payload_patch")
        target_fields = item.get("target_fields")
        if not variant_id or not name or category not in {"happy_path", "negative_path", "boundary_path", "auth"}:
            return None
        if not isinstance(payload_patch, dict):
            return None
        if not isinstance(target_fields, list):
            return None
        normalized_target_fields = [str(field).strip() for field in target_fields if str(field).strip()]
        return {
            "variant_id": variant_id,
            "name": name,
            "category": category,
            "payload_patch": payload_patch,
            "target_fields": normalized_target_fields,
            "reason": str(item.get("reason") or "建议补充该测试数据变体以增强输入覆盖。"),
            "suggested_assertions": [entry for entry in item.get("suggested_assertions") or [] if isinstance(entry, dict)],
            "confidence": self._normalize_confidence(item.get("confidence"), fallback=0.82),
        }

    def _variant_key(self, item: dict[str, Any]) -> str:
        return "|".join(
            [
                str(item.get("variant_id") or ""),
                str(item.get("name") or ""),
                ",".join(str(field) for field in item.get("target_fields") or []),
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

    def _downgrade_to_draft_variant(self, item: dict[str, Any]) -> dict[str, Any]:
        draft_item = dict(item)
        draft_item["confidence"] = min(self._normalize_confidence(draft_item.get("confidence"), fallback=0.62), 0.62)
        reason = str(draft_item.get("reason") or "").strip()
        if reason and "草案" not in reason:
            draft_item["reason"] = f"{reason} 当前缺少规则保底，此变体为低可信度草案。"
        elif not reason:
            draft_item["reason"] = "当前缺少规则保底，此变体为基于上下文推断的低可信度草案。"
        return draft_item

    def _normalize_confidence(self, value: Any, *, fallback: float) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return fallback
        return max(0.0, min(1.0, confidence))
