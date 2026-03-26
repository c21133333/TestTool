from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException

from backend.app.schemas.ai_copilot import AiTestPointRead, AiTestPointResult
from backend.app.services.ai_test_point_llm_service import AiTestPointLlmService
from backend.app.services.markdown_endpoint_parser import MarkdownEndpointParser

_CORE_POINT_CATEGORIES = ("happy_path", "negative_path", "boundary_path")
_POINT_CATEGORIES = (
    "happy_path",
    "negative_path",
    "boundary_path",
    "auth",
    "idempotent",
    "pagination",
    "assertion_hardening",
)
_ASSERTION_HINT_DIMENSIONS = ("status", "business_code", "body_field", "schema", "latency")
_CATEGORY_ALIASES = {
    "happy_path": ("happy_path", "mainline", "happy path", "主流程"),
    "negative_path": ("negative_path", "negative path", "failure path", "异常流程", "失败路径"),
    "boundary_path": ("boundary_path", "boundary path", "边界场景"),
    "auth": ("auth", "authorization", "authentication", "鉴权场景", "鉴权"),
    "idempotent": ("idempotent", "幂等场景", "幂等"),
    "pagination": ("pagination", "page", "分页场景", "分页"),
    "assertion_hardening": (
        "assertion_hardening",
        "assertion",
        "assertions_json",
        "status code assertion",
        "business code assertion",
        "body field assertion",
        "schema assertion",
        "latency assertion",
        "断言加固",
        "状态码断言",
        "业务码断言",
        "响应字段断言",
        "响应结构断言",
        "时延断言",
        "断言",
    ),
}
_CONFIG_ERROR_DETAILS = {
    "AI endpoint is required.",
    "AI model is required.",
    "AI API key is required.",
}
_CATEGORY_LABELS = {
    "happy_path": "主流程",
    "negative_path": "异常流程",
    "boundary_path": "边界场景",
    "auth": "鉴权场景",
    "idempotent": "幂等场景",
    "pagination": "分页场景",
    "assertion_hardening": "断言加固",
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
        coverage_missing_dimensions = context.get("coverage_missing_dimensions") if isinstance(context.get("coverage_missing_dimensions"), list) else []
        enable_llm = bool(context.get("enable_llm"))
        input_snapshot = context.get("input_snapshot") if isinstance(context.get("input_snapshot"), dict) else {}
        requested_category_map = self._build_requested_category_map(
            prompt_hints=prompt_hints,
            coverage_missing_dimensions=coverage_missing_dimensions,
        )

        baseline_points, baseline_warnings = self._build_rule_points(
            input_snapshot=input_snapshot,
            markdown_text=markdown_text,
            requested_category_map=requested_category_map,
        )
        baseline_payload = [item.model_dump() for item in baseline_points]
        has_rule_baseline = bool(baseline_payload)
        missing_required_pairs = self._missing_required_pairs(
            requested_category_map=requested_category_map,
            points=baseline_payload,
        )

        warnings = list(baseline_warnings)
        merged_points = list(baseline_payload)
        call_trace: dict[str, Any] = {"call_mode": "deterministic", "trace_json": {}}

        if enable_llm:
            try:
                runtime = self._llm_service.resolve_runtime()
                merged_points, llm_warnings, call_trace = self._run_llm_enhancement(
                    runtime=runtime,
                    input_snapshot=input_snapshot,
                    baseline_payload=baseline_payload,
                    markdown_text=markdown_text,
                    prompt_hints=prompt_hints,
                    has_rule_baseline=has_rule_baseline,
                    missing_required_pairs=missing_required_pairs,
                )
                warnings = self._merge_warnings(
                    baseline_warnings=baseline_warnings,
                    llm_warnings=llm_warnings,
                    has_rule_baseline=has_rule_baseline,
                    draft_warning="当前测试点未获得规则基线支撑，可信度较低，请在落草稿前人工复核。",
                )
            except HTTPException as exc:
                warnings = self._merge_warnings(
                    baseline_warnings=baseline_warnings,
                    llm_warnings=self._warnings_for_llm_failure(exc, has_rule_baseline=has_rule_baseline),
                    has_rule_baseline=has_rule_baseline,
                    draft_warning="当前测试点未获得规则基线支撑，可信度较低，请在落草稿前人工复核。",
                )
                call_trace = self._build_fallback_call_trace(exc)

        if not has_rule_baseline:
            merged_points = [self._downgrade_to_draft_point(item) for item in merged_points]
        if not merged_points and not warnings:
            warnings = ["当前上下文不足，暂时无法生成测试点。"]

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
        requested_category_map: dict[str, set[str]],
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
            warnings.append("当前上下文没有识别到可用于生成测试点的接口候选。")

        test_points: list[AiTestPointRead] = []
        for method, path in endpoints:
            coverage_categories = coverage_map.get(f"{method} {path}", set())
            for category in self._categories_for_endpoint(method, path, requested_category_map):
                test_points.append(
                    AiTestPointRead(
                        id=f"tp_{method.lower()}_{path.strip('/').replace('/', '_').replace('-', '_').replace(':', '_') or 'root'}_{category}",
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

    def _build_requested_category_map(
        self,
        *,
        prompt_hints: str,
        coverage_missing_dimensions: list[dict[str, Any]],
    ) -> dict[str, set[str]]:
        return self._merge_category_maps(
            self._build_prompt_category_map(prompt_hints=prompt_hints),
            self._build_structured_category_map(coverage_missing_dimensions=coverage_missing_dimensions),
        )

    def _categories_for_endpoint(
        self,
        method: str,
        path: str,
        prompt_category_map: dict[str, set[str]],
    ) -> tuple[str, ...]:
        endpoint_keys = self._endpoint_keys_for_lookup(method, path)
        ordered = list(_CORE_POINT_CATEGORIES)
        for category in sorted(prompt_category_map.get("*", set())):
            if category not in ordered:
                ordered.append(category)
        for endpoint_key in endpoint_keys:
            for category in sorted(prompt_category_map.get(endpoint_key, set())):
                if category not in ordered:
                    ordered.append(category)
        return tuple(ordered)

    def _merge_category_maps(self, *maps: dict[str, set[str]]) -> dict[str, set[str]]:
        merged: dict[str, set[str]] = {}
        for category_map in maps:
            for endpoint_key, categories in category_map.items():
                if not categories:
                    continue
                merged.setdefault(endpoint_key, set()).update(categories)
        return merged

    def _build_prompt_category_map(self, *, prompt_hints: str) -> dict[str, set[str]]:
        lines = [line.strip() for line in prompt_hints.splitlines() if line.strip()]
        if not lines:
            return {}
        category_map: dict[str, set[str]] = {}
        for line in lines:
            categories = self._extract_categories_from_text(line)
            if not categories:
                continue
            endpoint_key = self._extract_endpoint_key_from_text(line)
            for candidate_key in self._expand_endpoint_key(endpoint_key):
                category_map.setdefault(candidate_key, set()).update(categories)
        return category_map

    def _build_structured_category_map(self, *, coverage_missing_dimensions: list[dict[str, Any]]) -> dict[str, set[str]]:
        if not coverage_missing_dimensions:
            return {}
        category_map: dict[str, set[str]] = {}
        for item in coverage_missing_dimensions:
            if not isinstance(item, dict):
                continue
            endpoint_text = str(item.get("endpoint") or "").strip()
            dimension = str(item.get("dimension") or "").strip()
            reason = str(item.get("reason") or "").strip()
            categories = self._categories_from_dimension(dimension=dimension, reason=reason)
            if not categories:
                continue
            endpoint_key = self._extract_endpoint_key_from_text(endpoint_text or reason)
            for candidate_key in self._expand_endpoint_key(endpoint_key):
                category_map.setdefault(candidate_key, set()).update(categories)
        return category_map

    def _categories_from_dimension(self, *, dimension: str, reason: str) -> set[str]:
        normalized_dimension = dimension.strip().lower()
        if normalized_dimension in _POINT_CATEGORIES:
            return {normalized_dimension}

        assertion_dimensions = {
            "status",
            "status_code",
            "business_code",
            "body_field",
            "response_field",
            "schema",
            "response_schema",
            "response_structure",
            "structure",
            "latency",
            "performance",
        }
        if normalized_dimension in assertion_dimensions:
            return {"assertion_hardening"}

        categories = self._extract_categories_from_text(f"{dimension} {reason}".strip())
        if normalized_dimension.endswith("_assertion") or normalized_dimension.endswith("_assert"):
            categories.add("assertion_hardening")
        return categories

    def _extract_categories_from_text(self, text: str) -> set[str]:
        lowered = text.lower()
        categories: set[str] = set()
        for category, aliases in _CATEGORY_ALIASES.items():
            if any(alias.lower() in lowered for alias in aliases):
                categories.add(category)
        if any(alias in lowered for alias in _ASSERTION_HINT_DIMENSIONS):
            categories.add("assertion_hardening")
        if any(token in lowered for token in ("status_code", "business_code", "response field", "response_field", "response structure", "response_structure")):
            categories.add("assertion_hardening")
        return categories

    def _extract_endpoint_key_from_text(self, text: str) -> str:
        match = re.search(r"\b(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(\S+)", text, re.IGNORECASE)
        if not match:
            return "*"
        method = match.group(1).upper()
        path = match.group(2).strip()
        return f"{method} {path}" if path else "*"

    def _endpoint_keys_for_lookup(self, method: str, path: str) -> tuple[str, ...]:
        raw_path = path.strip()
        if not raw_path:
            return (f"{method} {path}",)
        keys = [f"{method} {raw_path}"]
        parsed = urlparse(raw_path)
        if parsed.scheme and parsed.netloc:
            normalized_path = parsed.path or "/"
            if parsed.query:
                normalized_path = f"{normalized_path}?{parsed.query}"
            normalized_key = f"{method} {normalized_path}"
            if normalized_key not in keys:
                keys.append(normalized_key)
        return tuple(keys)

    def _expand_endpoint_key(self, endpoint_key: str) -> tuple[str, ...]:
        match = re.match(r"^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(.+)$", endpoint_key.strip(), re.IGNORECASE)
        if not match:
            return (endpoint_key,)
        method = match.group(1).upper()
        path = match.group(2).strip()
        return self._endpoint_keys_for_lookup(method, path)

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
            coverage_map[f"{method} {path}"] = set(_CORE_POINT_CATEGORIES)
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
        if category in {"happy_path", "auth"}:
            return "high"
        if category in {"negative_path", "boundary_path", "idempotent", "pagination"}:
            return "medium"
        return "low"

    def _suggested_case_count_for_category(self, category: str) -> int:
        if category in {"happy_path", "auth", "assertion_hardening"}:
            return 1
        return 2

    def _baseline_confidence(self, category: str, covered_by_existing_cases: bool) -> float:
        if covered_by_existing_cases:
            return 0.94
        if category in {"happy_path", "auth"}:
            return 0.88
        if category == "assertion_hardening":
            return 0.82
        return 0.84

    def _reason_for_point(self, method: str, path: str, category: str, endpoint_exists: bool) -> str:
        category_label = _CATEGORY_LABELS.get(category, category)
        if endpoint_exists:
            return f"现有上下文已出现 {method} {path}，建议围绕“{category_label}”补齐或重新标记用例，确保覆盖结果可被系统识别。"
        return f"提供的接口线索中包含 {method} {path}，建议补充“{category_label}”相关测试设计，避免该维度长期缺口。"

    def _run_llm_enhancement(
        self,
        *,
        runtime: Any,
        input_snapshot: dict[str, Any],
        baseline_payload: list[dict[str, Any]],
        markdown_text: str,
        prompt_hints: str,
        has_rule_baseline: bool,
        missing_required_pairs: list[dict[str, str]],
    ) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
        attempt_count = 0
        warnings: list[str] = []
        first_failure: HTTPException | None = None
        merged_points = list(baseline_payload)

        for enforce_required_pairs in (bool(missing_required_pairs), True):
            if enforce_required_pairs and not missing_required_pairs:
                continue
            attempt_count += 1
            try:
                llm_points, llm_warnings = self._llm_service.analyze_points(
                    runtime=runtime,
                    input_snapshot=input_snapshot,
                    baseline_points=merged_points,
                    markdown_text=markdown_text,
                    prompt_hints=prompt_hints,
                    has_rule_baseline=has_rule_baseline,
                    required_pairs=missing_required_pairs,
                    enforce_required_pairs=enforce_required_pairs,
                )
            except HTTPException as exc:
                if first_failure is None:
                    first_failure = exc
                if exc.detail in _CONFIG_ERROR_DETAILS:
                    raise
                if attempt_count >= 2:
                    raise exc
                continue

            merged_points = self._merge_points(
                baseline_points=merged_points,
                llm_points=llm_points,
            )
            warnings = self._merge_retry_warnings(
                current_warnings=warnings,
                next_warnings=llm_warnings,
                retry_used=attempt_count > 1,
                first_failure=first_failure,
            )
            remaining_required_pairs = self._missing_required_pairs(
                requested_category_map=self._required_pairs_to_category_map(missing_required_pairs),
                points=merged_points,
            )
            call_trace = dict(self._llm_service.last_call_trace or {"call_mode": "llm", "trace_json": {}})
            call_trace.setdefault("trace_json", {})
            call_trace["trace_json"] = {
                **(call_trace.get("trace_json") or {}),
                "attempt_count": attempt_count,
                "retry_used": attempt_count > 1,
                "required_pair_count": len(missing_required_pairs),
                "remaining_required_pair_count": len(remaining_required_pairs),
            }
            if first_failure is not None:
                call_trace["trace_json"]["retry_recovered_from"] = str(first_failure.detail or first_failure.status_code)
            if not remaining_required_pairs:
                return merged_points, warnings, call_trace
            if attempt_count >= 2:
                warnings = self._merge_retry_warnings(
                    current_warnings=warnings,
                    next_warnings=[
                        "LLM 已完成增强，但重试后仍有部分指定 coverage 类别未补齐，请人工补充确认。"
                    ],
                    retry_used=True,
                    first_failure=first_failure,
                )
                call_trace["trace_json"]["missing_required_pairs"] = remaining_required_pairs
                return merged_points, warnings, call_trace
            missing_required_pairs = remaining_required_pairs

        if first_failure is not None:
            raise first_failure
        return merged_points, warnings, {"call_mode": "deterministic", "trace_json": {}}

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
        reason = str(item.get("reason") or "").strip() or f"建议补充或复核“{title}”对应的覆盖设计。"
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

    def _merge_retry_warnings(
        self,
        *,
        current_warnings: list[str],
        next_warnings: list[str],
        retry_used: bool,
        first_failure: HTTPException | None,
    ) -> list[str]:
        merged = self._merge_warnings(
            baseline_warnings=current_warnings,
            llm_warnings=next_warnings,
            has_rule_baseline=True,
            draft_warning="",
        )
        if retry_used and first_failure is not None:
            retry_warning = f"LLM 首次调用失败后已自动重试成功。原因：{first_failure.detail or first_failure.status_code}"
            if retry_warning not in merged:
                merged.append(retry_warning)
        return merged

    def _required_pairs_to_category_map(self, required_pairs: list[dict[str, str]]) -> dict[str, set[str]]:
        category_map: dict[str, set[str]] = {}
        for item in required_pairs:
            endpoint = str(item.get("endpoint") or "").strip()
            category = str(item.get("category") or "").strip()
            if not endpoint or category not in _POINT_CATEGORIES:
                continue
            category_map.setdefault(endpoint, set()).add(category)
        return category_map

    def _missing_required_pairs(
        self,
        *,
        requested_category_map: dict[str, set[str]],
        points: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        existing_pairs: set[tuple[str, str]] = set()
        for item in points:
            title = str(item.get("title") or "").strip()
            category = str(item.get("category") or "").strip()
            endpoint = self._extract_endpoint_from_point_title(title)
            if endpoint and category in _POINT_CATEGORIES:
                existing_pairs.add((endpoint, category))

        missing_pairs: list[dict[str, str]] = []
        for endpoint_key, categories in requested_category_map.items():
            if endpoint_key == "*":
                continue
            for category in sorted(categories):
                if category not in _POINT_CATEGORIES:
                    continue
                if (endpoint_key, category) not in existing_pairs:
                    missing_pairs.append({"endpoint": endpoint_key, "category": category})
        return missing_pairs

    def _extract_endpoint_from_point_title(self, title: str) -> str:
        match = re.match(r"^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(.+)\s+([a-z_]+)$", title.strip(), re.IGNORECASE)
        if not match:
            return ""
        method = match.group(1).upper()
        path = match.group(2).strip()
        if not path:
            return ""
        return f"{method} {path}"

    def _warnings_for_llm_failure(self, exc: HTTPException, *, has_rule_baseline: bool) -> list[str]:
        detail = str(exc.detail or "").strip()
        if has_rule_baseline and detail in _CONFIG_ERROR_DETAILS:
            return []
        if has_rule_baseline:
            return [f"当前无法使用 LLM 增强，本次仅返回规则生成的测试点。原因：{detail or exc.status_code}"]
        return [f"当前无法使用 LLM 生成测试点。原因：{detail or exc.status_code}"]

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
        if reason and "可信度较低" not in reason:
            draft_item["reason"] = f"{reason} 当前测试点仅为草案级建议，可信度较低，建议人工复核后再落草稿。"
        elif not reason:
            draft_item["reason"] = "当前测试点仅为草案级建议，可信度较低，建议人工复核后再落草稿。"
        return draft_item

    def _normalize_confidence(self, value: Any, *, fallback: float) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return fallback
        return max(0.0, min(1.0, confidence))
