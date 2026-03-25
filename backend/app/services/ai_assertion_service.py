from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.schemas.ai_copilot import AiArtifactStatus
from backend.app.services.ai_artifact_service import AiArtifactService
from backend.app.services.ai_assertion_llm_service import AiAssertionLlmService
from backend.app.services.workspace_service import WorkspaceService


class AiAssertionService:
    def __init__(
        self,
        session: Session | None = None,
        *,
        llm_service: AiAssertionLlmService | None = None,
    ) -> None:
        self._session = session
        self._llm_service = llm_service or AiAssertionLlmService()

    def generate_preview(self, context: dict[str, Any]) -> dict[str, Any]:
        snapshot = context.get("input_snapshot") if isinstance(context.get("input_snapshot"), dict) else {}
        existing_assertions = [item for item in snapshot.get("assertions_json") or [] if isinstance(item, dict)]
        baseline_suggestions, baseline_warnings = self._build_baseline_suggestions(snapshot, existing_assertions)
        recent_success_sample = snapshot.get("recent_success_sample") if isinstance(snapshot.get("recent_success_sample"), dict) else {}
        has_success_sample = bool(recent_success_sample)

        runtime = self._llm_service.resolve_runtime()
        llm_suggestions, llm_warnings = self._llm_service.analyze_assertions(
            runtime=runtime,
            input_snapshot=snapshot,
            baseline_suggestions=baseline_suggestions,
            existing_assertions=existing_assertions,
            has_success_sample=has_success_sample,
        )
        merged_suggestions = self._merge_suggestions(
            baseline_suggestions=baseline_suggestions,
            llm_suggestions=llm_suggestions,
            existing_assertions=existing_assertions,
        )
        if not has_success_sample:
            merged_suggestions = [self._downgrade_to_draft_suggestion(item) for item in merged_suggestions]
        warnings = self._merge_warnings(
            baseline_warnings=baseline_warnings,
            llm_warnings=llm_warnings,
            has_success_sample=has_success_sample,
        )
        if not merged_suggestions and not warnings:
            warnings = (
                ["当前未能生成可直接应用的新断言建议，请结合最近成功样本人工确认。"]
                if has_success_sample
                else ["当前未能生成可直接应用的草案断言，请补充请求信息或先执行一次用例后再试。"]
            )
        return {
            "result": {"suggested_assertions": merged_suggestions},
            "warnings": warnings,
            "call_trace": self._llm_service.last_call_trace,
        }

    def apply_artifact(self, artifact_id: str, *, override_existing: bool = False):
        if self._session is None:
            raise RuntimeError("AiAssertionService.apply_artifact requires a database session.")

        artifact_service = AiArtifactService(self._session)
        artifact = artifact_service.accept_artifact(artifact_id)
        if artifact.capability != "assertion":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI 产物能力类型不匹配。")
        if artifact.case_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI 产物没有绑定到用例。")

        workspace = WorkspaceService(self._session)
        api_case = workspace.get_case(artifact.case_id)
        suggested_assertions = [item for item in (artifact.output_json or {}).get("suggested_assertions", []) if isinstance(item, dict)]
        existing_assertions = [item for item in (api_case.assertions_json or []) if isinstance(item, dict)]

        if override_existing:
            next_assertions = suggested_assertions
        else:
            seen_keys = {self._assertion_key(item) for item in existing_assertions}
            appended = list(existing_assertions)
            for suggestion in suggested_assertions:
                key = self._assertion_key(suggestion)
                if key in seen_keys:
                    continue
                appended.append(suggestion)
                seen_keys.add(key)
            next_assertions = appended

        api_case.assertions_json = next_assertions
        saved = workspace.save_case(api_case)
        artifact.status = AiArtifactStatus.applied.value
        artifact_service.save(artifact)
        return saved

    def _build_baseline_suggestions(
        self,
        snapshot: dict[str, Any],
        existing_assertions: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        recent_success_sample = snapshot.get("recent_success_sample") if isinstance(snapshot.get("recent_success_sample"), dict) else {}
        response = recent_success_sample.get("response") if isinstance(recent_success_sample.get("response"), dict) else {}
        response_body = response.get("response_json") if isinstance(response.get("response_json"), dict) else {}
        status_code = response.get("status_code")

        seen_keys = {self._assertion_key(item) for item in existing_assertions}
        suggestions: list[dict[str, Any]] = []
        warnings: list[str] = []

        if not recent_success_sample:
            warnings.append("没有找到最近一次成功执行样本，以下建议将基于请求结构推断，仅可作为草案参考。")
            return suggestions, warnings

        if status_code is not None:
            candidate = {
                "type": "status_code",
                "operator": "==",
                "expected": status_code,
                "enabled": True,
                "reason": "建议先固定最近一次成功执行的状态码，作为最基础的成功断言。",
                "confidence": 0.96,
            }
            if self._assertion_key(candidate) not in seen_keys:
                suggestions.append(candidate)
                seen_keys.add(self._assertion_key(candidate))

        for path, value in self._collect_scalar_paths(response_body):
            candidate = {
                "type": "json_path",
                "path": path,
                "operator": "==",
                "expected": value,
                "enabled": True,
                "reason": f"最近一次成功样本里字段 {path} 表现稳定，适合作为返回值断言。",
                "confidence": self._confidence_for(value),
            }
            key = self._assertion_key(candidate)
            if key in seen_keys:
                continue
            suggestions.append(candidate)
            seen_keys.add(key)
            if len(suggestions) >= 4:
                break

        if not suggestions:
            warnings.append("最近成功样本中没有提炼出新的非重复断言建议。")

        return suggestions, warnings

    def _merge_suggestions(
        self,
        *,
        baseline_suggestions: list[dict[str, Any]],
        llm_suggestions: list[dict[str, Any]],
        existing_assertions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        existing_keys = {self._assertion_key(item) for item in existing_assertions}
        merged_by_key: dict[str, dict[str, Any]] = {}
        ordered_keys: list[str] = []

        for candidate in baseline_suggestions:
            key = self._assertion_key(candidate)
            if key in existing_keys:
                continue
            merged_by_key[key] = dict(candidate)
            ordered_keys.append(key)

        for candidate in llm_suggestions:
            normalized = self._normalize_llm_suggestion(candidate)
            if normalized is None:
                continue
            key = self._assertion_key(normalized)
            if key in existing_keys:
                continue
            if key not in merged_by_key:
                ordered_keys.append(key)
            merged_by_key[key] = normalized

        return [merged_by_key[key] for key in ordered_keys[:6]]

    def _normalize_llm_suggestion(self, suggestion: dict[str, Any]) -> dict[str, Any] | None:
        assertion_type = str(suggestion.get("type") or "").strip()
        operator = str(suggestion.get("operator") or "").strip()
        if assertion_type not in {"status_code", "json_path"}:
            return None
        if operator not in {"==", "contains", "not_null"}:
            return None

        normalized: dict[str, Any] = {
            "type": assertion_type,
            "operator": operator,
            "expected": suggestion.get("expected"),
            "enabled": suggestion.get("enabled") is not False,
            "reason": str(suggestion.get("reason") or "建议补充该断言以增强响应校验。"),
            "confidence": self._normalize_confidence(suggestion.get("confidence")),
        }
        if assertion_type == "json_path":
            path = str(suggestion.get("path") or "").strip()
            if not path:
                return None
            normalized["path"] = path
        return normalized

    def _collect_scalar_paths(self, value: Any, *, prefix: str = "$", depth: int = 0) -> list[tuple[str, Any]]:
        if depth > 2:
            return []
        if not isinstance(value, dict):
            return []

        collected: list[tuple[str, Any]] = []
        for key, item in value.items():
            path = f"{prefix}.{key}"
            if isinstance(item, dict):
                collected.extend(self._collect_scalar_paths(item, prefix=path, depth=depth + 1))
                continue
            if isinstance(item, list) or item is None:
                continue
            if isinstance(item, str) and len(item.strip()) > 80:
                continue
            collected.append((path, item))
            if len(collected) >= 3:
                break
        return collected

    def _assertion_key(self, assertion: dict[str, Any]) -> str:
        normalized_expected = repr(assertion.get("expected"))
        return "|".join(
            [
                str(assertion.get("type") or ""),
                str(assertion.get("operator") or ""),
                str(assertion.get("path") or ""),
                str(assertion.get("header") or ""),
                normalized_expected,
            ]
        )

    def _confidence_for(self, value: Any) -> float:
        if isinstance(value, (bool, int, float)):
            return 0.9
        if isinstance(value, str) and len(value) <= 16:
            return 0.82
        return 0.74

    def _normalize_confidence(self, value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.75
        return max(0.0, min(1.0, confidence))

    def _merge_warnings(
        self,
        *,
        baseline_warnings: list[str],
        llm_warnings: list[str],
        has_success_sample: bool,
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
        if not has_success_sample:
            _append(["以下建议未基于真实成功响应验证，请人工确认后再应用。"])
        return ordered

    def _downgrade_to_draft_suggestion(self, suggestion: dict[str, Any]) -> dict[str, Any]:
        draft_suggestion = dict(suggestion)
        draft_suggestion["confidence"] = min(self._normalize_confidence(draft_suggestion.get("confidence")), 0.68)
        reason = str(draft_suggestion.get("reason") or "").strip()
        if reason and "草案" not in reason:
            draft_suggestion["reason"] = f"{reason} 当前无成功样本支撑，此断言为草案建议。"
        elif not reason:
            draft_suggestion["reason"] = "当前无成功样本支撑，此断言为基于请求结构推断的草案建议。"
        return draft_suggestion
