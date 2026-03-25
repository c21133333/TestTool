from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.app.schemas.ai_copilot import AiTestPointRead, AiTestPointResult
from backend.app.services.ai_test_point_llm_service import AiTestPointLlmService
from backend.app.services.markdown_endpoint_parser import MarkdownEndpointParser

_POINT_CATEGORIES = ("happy_path", "negative_path", "boundary_path")
_CONFIG_ERROR_DETAILS = {
    "AI endpoint is required.",
    "AI model is required.",
    "AI API key is required.",
}


class AiTestPointService:
    def __init__(
        self,
        session,
        *,
        parser: MarkdownEndpointParser | None = None,
        llm_service: AiTestPointLlmService | None = None,
    ) -> None:
        self._parser = parser or MarkdownEndpointParser()
        self._llm_service = llm_service or AiTestPointLlmService()

    def generate_preview(self, context: dict[str, Any]) -> dict[str, Any]:
        markdown_text = str(context.get("markdown_text") or "").strip()
        prompt_hints = str(context.get("prompt_hints") or "").strip()
        enable_llm = bool(context.get("enable_llm"))
        input_snapshot = context.get("input_snapshot") if isinstance(context.get("input_snapshot"), dict) else {}

        baseline_points, baseline_warnings = self._build_rule_points(
            input_snapshot=input_snapshot,
            markdown_text=markdown_text,
        )
        baseline_payload = [item.model_dump() for item in baseline_points]
        has_rule_baseline = bool(baseline_payload)

        warnings = list(baseline_warnings)
        merged_points = list(baseline_payload)
        call_trace: dict[str, Any] = {"call_mode": "deterministic", "trace_json": {}}

        if enable_llm:
            try:
                runtime = self._llm_service.resolve_runtime()
                llm_points, llm_warnings = self._llm_service.analyze_points(
                    runtime=runtime,
                    input_snapshot=input_snapshot,
                    baseline_points=baseline_payload,
                    markdown_text=markdown_text,
                    prompt_hints=prompt_hints,
                    has_rule_baseline=has_rule_baseline,
                )
                merged_points = self._merge_points(
                    baseline_points=baseline_payload,
                    llm_points=llm_points,
                )
                warnings = self._merge_warnings(
                    baseline_warnings=baseline_warnings,
                    llm_warnings=llm_warnings,
                    has_rule_baseline=has_rule_baseline,
                    draft_warning="Generated test points are not backed by a deterministic baseline. Confidence is lower; review before generating drafts.",
                )
                call_trace = dict(self._llm_service.last_call_trace or call_trace)
            except HTTPException as exc:
                warnings = self._merge_warnings(
                    baseline_warnings=baseline_warnings,
                    llm_warnings=self._warnings_for_llm_failure(exc, has_rule_baseline=has_rule_baseline),
                    has_rule_baseline=has_rule_baseline,
                    draft_warning="Generated test points are not backed by a deterministic baseline. Confidence is lower; review before generating drafts.",
                )
                call_trace = self._build_fallback_call_trace(exc)

        if not has_rule_baseline:
            merged_points = [self._downgrade_to_draft_point(item) for item in merged_points]
        if not merged_points and not warnings:
            warnings = ["No test points could be generated from the available context."]

        return {
            "result": AiTestPointResult.model_validate({"test_points": merged_points}).model_dump(),
            "warnings": warnings,
            "call_trace": call_trace,
        }

    def _build_rule_points(
        self,
        *,
        input_snapshot: dict[str, Any],
        markdown_text: str,
    ) -> tuple[list[AiTestPointRead], list[str]]:
        warnings: list[str] = []
        endpoints = self._collect_target_endpoints(input_snapshot)
        coverage_map = self._build_existing_coverage_map(input_snapshot)

        if markdown_text:
            parsed = self._parser.parse(markdown_text)
            warnings.extend(parsed.warnings)
            markdown_endpoints = []
            for section in parsed.sections:
                markdown_endpoints.extend((match.method, match.path) for match in section.endpoint_matches)
            if markdown_endpoints:
                endpoints = self._dedupe_endpoints(markdown_endpoints)
        if not endpoints:
            warnings.append("No endpoint candidates were found for test point generation.")

        test_points: list[AiTestPointRead] = []
        for method, path in endpoints:
            coverage_categories = coverage_map.get(f"{method} {path}", set())
            for category in _POINT_CATEGORIES:
                test_points.append(
                    AiTestPointRead(
                        id=f"tp_{method.lower()}_{path.strip('/').replace('/', '_').replace('-', '_') or 'root'}_{category}",
                        title=f"{method} {path} {category}",
                        category=category,
                        risk_level=self._risk_level_for_category(category),
                        reason=self._reason_for_point(method, path, category, bool(coverage_categories)),
                        covered_by_existing_cases=category in coverage_categories,
                        suggested_case_count=self._suggested_case_count_for_category(category),
                        confidence=self._baseline_confidence(category, category in coverage_categories),
                    )
                )

        return test_points, warnings

    def _collect_target_endpoints(self, input_snapshot: dict) -> list[tuple[str, str]]:
        unique_endpoints = []
        case_summary = input_snapshot.get("case_summary") if isinstance(input_snapshot.get("case_summary"), dict) else {}
        for item in case_summary.get("unique_endpoints") or []:
            if not isinstance(item, dict):
                continue
            method = str(item.get("method") or "").strip().upper()
            path = str(item.get("path") or "").strip()
            if method and path:
                unique_endpoints.append((method, path))
        return self._dedupe_endpoints(unique_endpoints)

    def _build_existing_coverage_map(self, input_snapshot: dict) -> dict[str, set[str]]:
        coverage_map: dict[str, set[str]] = {}
        cases = input_snapshot.get("cases") if isinstance(input_snapshot.get("cases"), list) else []
        if cases:
            for case in cases:
                if not isinstance(case, dict):
                    continue
                method = str(case.get("method") or "").strip().upper()
                path = str(case.get("url") or "").strip()
                if not method or not path:
                    continue
                coverage_map.setdefault(f"{method} {path}", set()).update(self._extract_case_categories(case))
            return coverage_map

        for method, path in self._collect_target_endpoints(input_snapshot):
            coverage_map[f"{method} {path}"] = set(_POINT_CATEGORIES)
        return coverage_map

    def _extract_case_categories(self, case: dict) -> set[str]:
        metadata = case.get("metadata_json") if isinstance(case.get("metadata_json"), dict) else {}
        categories: set[str] = set()
        category = str(metadata.get("category") or "").strip()
        if category in _POINT_CATEGORIES:
            categories.add(category)
        raw_tags = metadata.get("tags")
        if isinstance(raw_tags, list):
            for tag in raw_tags:
                normalized = str(tag).strip()
                if normalized in _POINT_CATEGORIES:
                    categories.add(normalized)
        elif isinstance(raw_tags, str) and raw_tags.strip() in _POINT_CATEGORIES:
            categories.add(raw_tags.strip())
        return categories

    def _dedupe_endpoints(self, endpoints: list[tuple[str, str]]) -> list[tuple[str, str]]:
        ordered: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for method, path in endpoints:
            key = (method.strip().upper(), path.strip())
            if not key[0] or not key[1] or key in seen:
                continue
            seen.add(key)
            ordered.append(key)
        return ordered

    def _risk_level_for_category(self, category: str) -> str:
        if category == "happy_path":
            return "high"
        if category == "negative_path":
            return "medium"
        return "medium"

    def _suggested_case_count_for_category(self, category: str) -> int:
        if category == "happy_path":
            return 1
        return 2

    def _baseline_confidence(self, category: str, covered_by_existing_cases: bool) -> float:
        if covered_by_existing_cases:
            return 0.94
        if category == "happy_path":
            return 0.88
        return 0.84

    def _reason_for_point(self, method: str, path: str, category: str, endpoint_exists: bool) -> str:
        if endpoint_exists:
            return f"{method} {path} should be reviewed for {category} coverage against existing cases."
        return f"{method} {path} appears in the provided spec and should add {category} coverage."

    def _merge_points(
        self,
        *,
        baseline_points: list[dict[str, Any]],
        llm_points: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged_by_key: dict[str, dict[str, Any]] = {}
        ordered_keys: list[str] = []

        for item in baseline_points:
            normalized = self._normalize_point(item, fallback_confidence=0.88)
            if normalized is None:
                continue
            key = self._point_key(normalized)
            merged_by_key[key] = normalized
            ordered_keys.append(key)

        baseline_lookup = dict(merged_by_key)
        for item in llm_points:
            normalized = self._normalize_point(
                item,
                fallback_confidence=0.78,
                fallback_covered_lookup=baseline_lookup,
            )
            if normalized is None:
                continue
            key = self._point_key(normalized)
            if key not in merged_by_key:
                ordered_keys.append(key)
                merged_by_key[key] = normalized
                continue
            merged_by_key[key] = {**merged_by_key[key], **normalized}

        return [merged_by_key[key] for key in ordered_keys]

    def _normalize_point(
        self,
        item: dict[str, Any],
        *,
        fallback_confidence: float,
        fallback_covered_lookup: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        point_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        category = str(item.get("category") or "").strip()
        if not point_id or not title or category not in _POINT_CATEGORIES:
            return None

        risk_level = str(item.get("risk_level") or self._risk_level_for_category(category)).strip()
        reason = str(item.get("reason") or "").strip() or f"Review {title} coverage."
        covered_lookup = fallback_covered_lookup or {}
        covered_by_existing_cases = item.get("covered_by_existing_cases")
        if covered_by_existing_cases is None and point_id in covered_lookup:
            covered_by_existing_cases = covered_lookup[point_id].get("covered_by_existing_cases", False)
        suggested_case_count = item.get("suggested_case_count")
        try:
            suggested_case_count_value = int(suggested_case_count)
        except (TypeError, ValueError):
            suggested_case_count_value = self._suggested_case_count_for_category(category)

        return {
            "id": point_id,
            "title": title,
            "category": category,
            "risk_level": risk_level or self._risk_level_for_category(category),
            "reason": reason,
            "covered_by_existing_cases": bool(covered_by_existing_cases),
            "suggested_case_count": max(1, suggested_case_count_value),
            "confidence": self._normalize_confidence(item.get("confidence"), fallback=fallback_confidence),
        }

    def _point_key(self, item: dict[str, Any]) -> str:
        return str(item.get("id") or item.get("title") or "")

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

    def _warnings_for_llm_failure(self, exc: HTTPException, *, has_rule_baseline: bool) -> list[str]:
        detail = str(exc.detail or "").strip()
        if has_rule_baseline and detail in _CONFIG_ERROR_DETAILS:
            return []
        if has_rule_baseline:
            return [f"LLM enhancement is unavailable right now. Returned deterministic test points only. Detail: {detail or exc.status_code}"]
        return [f"LLM-generated test points are unavailable. Detail: {detail or exc.status_code}"]

    def _build_fallback_call_trace(self, exc: HTTPException) -> dict[str, Any]:
        detail = str(exc.detail or "").strip()
        failure_category = "llm_runtime_unavailable" if detail in _CONFIG_ERROR_DETAILS else "llm_fallback"
        return {
            "call_mode": "deterministic",
            "failure_category": failure_category,
            "trace_json": {
                "fallback_reason": detail or str(exc.status_code),
            },
        }

    def _downgrade_to_draft_point(self, item: dict[str, Any]) -> dict[str, Any]:
        draft_item = dict(item)
        draft_item["confidence"] = min(self._normalize_confidence(draft_item.get("confidence"), fallback=0.62), 0.62)
        reason = str(draft_item.get("reason") or "").strip()
        if reason and "low confidence" not in reason.lower():
            draft_item["reason"] = f"{reason} This point is draft-grade only and should be reviewed as low-confidence output."
        elif not reason:
            draft_item["reason"] = "This point is draft-grade only and should be reviewed as low-confidence output."
        return draft_item

    def _normalize_confidence(self, value: Any, *, fallback: float) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return fallback
        return max(0.0, min(1.0, confidence))
