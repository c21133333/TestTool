from __future__ import annotations

from typing import Any

from backend.app.schemas.ai_copilot import AiCoverageMissingDimension, AiCoverageResult, AiCoverageSuggestedPoint
from backend.app.services.ai_context_assembler import AiContextAssembler
from backend.app.services.ai_coverage_llm_service import AiCoverageLlmService
from backend.app.services.ai_coverage_scan_service import AiCoverageScanService

_SCENARIO_PRIORITY = {
    "happy_path": "high",
    "negative_path": "high",
    "boundary_path": "high",
    "auth": "high",
    "idempotent": "medium",
    "pagination": "medium",
}
_ASSERTION_PRIORITY = {
    "status": "high",
    "business_code": "high",
    "body_field": "medium",
    "schema": "medium",
    "latency": "medium",
}
_DIMENSION_LABELS = {
    "happy_path": "主流程",
    "negative_path": "异常流程",
    "boundary_path": "边界场景",
    "auth": "鉴权场景",
    "idempotent": "幂等场景",
    "pagination": "分页场景",
    "status": "状态码断言",
    "business_code": "业务码断言",
    "body_field": "响应字段断言",
    "schema": "响应结构断言",
    "latency": "时延断言",
}


class AiCoverageService:
    def __init__(
        self,
        session,
        *,
        scanner: AiCoverageScanService | None = None,
        llm_service: AiCoverageLlmService | None = None,
        context_assembler: AiContextAssembler | None = None,
    ) -> None:
        self._scanner = scanner or AiCoverageScanService(session)
        self._llm_service = llm_service or AiCoverageLlmService()
        self._context_assembler = context_assembler or AiContextAssembler(session)

    def generate_preview(self, context: dict[str, Any]) -> dict[str, Any]:
        target_type = str(context.get("target_type") or "").strip()
        target_id = int(context.get("target_id") or 0)
        input_snapshot = self._build_analysis_snapshot(
            target_type=target_type,
            target_id=target_id,
            input_snapshot=context.get("input_snapshot"),
        )
        scan_result = self._scanner.scan(target_type=target_type, target_id=target_id)
        runtime = self._llm_service.resolve_runtime()
        llm_result, warnings = self._llm_service.analyze_coverage(
            runtime=runtime,
            target_type=target_type,
            target_id=target_id,
            input_snapshot=input_snapshot,
            scan_result=scan_result,
        )
        result = self._merge_result(scan_result, llm_result)
        return {
            "result": result.model_dump(),
            "warnings": warnings,
            "call_trace": self._llm_service.last_call_trace,
        }

    def _build_analysis_snapshot(self, *, target_type: str, target_id: int, input_snapshot: Any) -> dict[str, Any]:
        snapshot = input_snapshot if isinstance(input_snapshot, dict) else {}
        if target_type != "project":
            return snapshot or self._context_assembler.build_context(
                capability="coverage",
                target_type=target_type,
                target_id=target_id,
            ).get("input_snapshot", {})

        project_snapshot = snapshot or self._context_assembler.build_project_context(target_id)
        suite_summaries = project_snapshot.get("suites") if isinstance(project_snapshot.get("suites"), list) else []
        suite_snapshots: list[dict[str, Any]] = []
        flattened_cases: list[dict[str, Any]] = []
        for suite_summary in suite_summaries:
            if not isinstance(suite_summary, dict):
                continue
            suite_id = int(suite_summary.get("suite_id") or 0)
            if suite_id <= 0:
                continue
            suite_snapshot = self._context_assembler.build_suite_context(suite_id)
            suite_cases = suite_snapshot.get("cases") if isinstance(suite_snapshot.get("cases"), list) else []
            suite_name = str(suite_snapshot.get("name") or "")
            suite_snapshots.append(
                {
                    "suite_id": suite_id,
                    "suite_name": suite_name,
                    "case_summary": suite_snapshot.get("case_summary") if isinstance(suite_snapshot.get("case_summary"), dict) else {},
                    "cases": suite_cases,
                }
            )
            for case in suite_cases:
                if not isinstance(case, dict):
                    continue
                flattened_cases.append({**case, "suite_id": suite_id, "suite_name": suite_name})
        return {
            **project_snapshot,
            "suite_snapshots": suite_snapshots,
            "cases": flattened_cases,
        }

    def _merge_result(self, scan_result: AiCoverageResult, llm_result: AiCoverageResult) -> AiCoverageResult:
        merged_missing = self._merge_missing_dimensions(scan_result, llm_result)
        merged_suggestions = llm_result.suggested_points or self._build_suggested_points(scan_result)
        return AiCoverageResult(
            coverage_score=scan_result.coverage_score,
            missing_dimensions=merged_missing,
            suggested_points=merged_suggestions,
        )

    def _merge_missing_dimensions(
        self,
        scan_result: AiCoverageResult,
        llm_result: AiCoverageResult,
    ) -> list[AiCoverageMissingDimension]:
        llm_reason_by_key = {
            (item.endpoint, item.dimension): item.reason
            for item in llm_result.missing_dimensions
        }
        merged: list[AiCoverageMissingDimension] = []
        for item in scan_result.missing_dimensions:
            merged.append(
                AiCoverageMissingDimension(
                    endpoint=item.endpoint,
                    dimension=item.dimension,
                    reason=str(llm_reason_by_key.get((item.endpoint, item.dimension)) or item.reason),
                )
            )
        return merged

    def _build_suggested_points(self, scan_result: AiCoverageResult) -> list[AiCoverageSuggestedPoint]:
        suggestions: list[AiCoverageSuggestedPoint] = []
        seen: set[tuple[str, str]] = set()
        for missing in scan_result.missing_dimensions:
            key = (missing.endpoint, missing.dimension)
            if key in seen:
                continue
            seen.add(key)
            suggestions.append(
                AiCoverageSuggestedPoint(
                    title=self._build_title(missing.endpoint, missing.dimension),
                    category=self._map_category(missing.dimension),
                    priority=self._map_priority(missing.dimension),
                    reason=missing.reason,
                )
            )
            if len(suggestions) >= 5:
                break
        return suggestions

    def _build_title(self, endpoint: str, dimension: str) -> str:
        return f"补充 {endpoint} 的{self._dimension_label(dimension)}覆盖"

    def _map_category(self, dimension: str) -> str:
        if dimension in _SCENARIO_PRIORITY:
            return dimension
        return "assertion_hardening"

    def _map_priority(self, dimension: str) -> str:
        if dimension in _SCENARIO_PRIORITY:
            return _SCENARIO_PRIORITY[dimension]
        return _ASSERTION_PRIORITY.get(dimension, "medium")

    def _dimension_label(self, dimension: str) -> str:
        return _DIMENSION_LABELS.get(dimension, dimension)
