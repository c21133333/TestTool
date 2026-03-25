from __future__ import annotations

from typing import Any

from backend.app.schemas.ai_copilot import AiCoverageResult, AiCoverageSuggestedPoint
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


class AiCoverageService:
    def __init__(self, session, *, scanner: AiCoverageScanService | None = None) -> None:
        self._scanner = scanner or AiCoverageScanService(session)

    def generate_preview(self, context: dict[str, Any]) -> dict[str, Any]:
        target_type = str(context.get("target_type") or "").strip()
        target_id = int(context.get("target_id") or 0)
        scan_result = self._scanner.scan(target_type=target_type, target_id=target_id)
        suggested_points = self._build_suggested_points(scan_result)
        result = AiCoverageResult(
            coverage_score=scan_result.coverage_score,
            missing_dimensions=scan_result.missing_dimensions,
            suggested_points=suggested_points,
        )
        return {
            "result": result.model_dump(),
            "warnings": [],
        }

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
        return f"{endpoint} {dimension} coverage gap"

    def _map_category(self, dimension: str) -> str:
        if dimension in _SCENARIO_PRIORITY:
            return dimension
        return "assertion_hardening"

    def _map_priority(self, dimension: str) -> str:
        if dimension in _SCENARIO_PRIORITY:
            return _SCENARIO_PRIORITY[dimension]
        return _ASSERTION_PRIORITY.get(dimension, "medium")
