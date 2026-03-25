from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from backend.app.schemas.ai_copilot import AiCoverageMissingDimension, AiCoverageResult
from backend.app.services.ai_context_assembler import AiContextAssembler

_SCENARIO_DIMENSIONS = (
    "happy_path",
    "negative_path",
    "boundary_path",
    "auth",
    "idempotent",
    "pagination",
)
_ASSERTION_DIMENSIONS = (
    "status",
    "business_code",
    "body_field",
    "schema",
    "latency",
)
_BUSINESS_CODE_PATHS = {"$.code", "$.status", "$.businessCode", "$.business_code"}
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


@dataclass
class _EndpointCoverage:
    scenarios: set[str] = field(default_factory=set)
    assertions: set[str] = field(default_factory=set)


class AiCoverageScanService:
    def __init__(self, session: Session, *, context_assembler: AiContextAssembler | None = None) -> None:
        self._context_assembler = context_assembler or AiContextAssembler(session)

    def scan(self, *, target_type: str, target_id: int) -> AiCoverageResult:
        endpoint_coverage = self._build_endpoint_coverage(target_type=target_type, target_id=target_id)
        if not endpoint_coverage:
            return AiCoverageResult(coverage_score=0, missing_dimensions=[], suggested_points=[])

        covered_scenarios = sorted({scenario for bucket in endpoint_coverage.values() for scenario in bucket.scenarios})
        covered_assertions = sorted({assertion for bucket in endpoint_coverage.values() for assertion in bucket.assertions})
        covered_slots = len(covered_scenarios) + len(covered_assertions)
        total_slots = len(_SCENARIO_DIMENSIONS) + len(_ASSERTION_DIMENSIONS)
        coverage_score = round((covered_slots / total_slots) * 100) if total_slots else 0

        missing_dimensions: list[AiCoverageMissingDimension] = []
        for endpoint in sorted(endpoint_coverage):
            bucket = endpoint_coverage[endpoint]
            for dimension in _SCENARIO_DIMENSIONS:
                if dimension not in bucket.scenarios:
                    missing_dimensions.append(
                        AiCoverageMissingDimension(
                            endpoint=endpoint,
                            dimension=dimension,
                            reason=f"现有用例元数据没有明确标记 {endpoint} 已覆盖“{self._dimension_label(dimension)}”。",
                        )
                    )
            for dimension in _ASSERTION_DIMENSIONS:
                if dimension not in bucket.assertions:
                    missing_dimensions.append(
                        AiCoverageMissingDimension(
                            endpoint=endpoint,
                            dimension=dimension,
                            reason=f"现有断言中没有任何配置可以证明 {endpoint} 已覆盖“{self._dimension_label(dimension)}”。",
                        )
                    )

        return AiCoverageResult(
            coverage_score=coverage_score,
            missing_dimensions=missing_dimensions,
            suggested_points=[],
        )

    def _build_endpoint_coverage(self, *, target_type: str, target_id: int) -> dict[str, _EndpointCoverage]:
        if target_type == "suite":
            suite_context = self._context_assembler.build_suite_context(target_id)
            cases = suite_context.get("cases") or []
            return self._collect_endpoint_coverage(cases)
        if target_type == "project":
            project_context = self._context_assembler.build_project_context(target_id)
            endpoint_coverage: dict[str, _EndpointCoverage] = {}
            for suite_summary in project_context.get("suites") or []:
                suite_id = int(suite_summary.get("suite_id") or 0)
                if suite_id <= 0:
                    continue
                suite_context = self._context_assembler.build_suite_context(suite_id)
                for endpoint, bucket in self._collect_endpoint_coverage(suite_context.get("cases") or []).items():
                    aggregate_bucket = endpoint_coverage.setdefault(endpoint, _EndpointCoverage())
                    aggregate_bucket.scenarios.update(bucket.scenarios)
                    aggregate_bucket.assertions.update(bucket.assertions)
            return endpoint_coverage
        raise ValueError(f"Unsupported coverage target_type: {target_type}")

    def _collect_endpoint_coverage(self, cases: list[dict]) -> dict[str, _EndpointCoverage]:
        endpoint_coverage: dict[str, _EndpointCoverage] = {}
        for case in cases:
            method = str(case.get("method") or "").strip().upper()
            path = str(case.get("url") or "").strip()
            if not method or not path:
                continue
            endpoint = f"{method} {path}"
            bucket = endpoint_coverage.setdefault(endpoint, _EndpointCoverage())
            bucket.scenarios.update(self._extract_scenarios(case))
            bucket.assertions.update(self._extract_assertions(case))
        return endpoint_coverage

    def _extract_scenarios(self, case: dict) -> set[str]:
        metadata = case.get("metadata_json") if isinstance(case.get("metadata_json"), dict) else {}
        scenarios: set[str] = set()

        category = str(metadata.get("category") or "").strip()
        if category in _SCENARIO_DIMENSIONS:
            scenarios.add(category)

        raw_tags = metadata.get("tags")
        if isinstance(raw_tags, list):
            tags = [str(tag).strip() for tag in raw_tags]
        elif isinstance(raw_tags, str):
            tags = [raw_tags.strip()]
        else:
            tags = []
        for tag in tags:
            if tag in _SCENARIO_DIMENSIONS:
                scenarios.add(tag)
        return scenarios

    def _extract_assertions(self, case: dict) -> set[str]:
        assertions = case.get("assertions_json") if isinstance(case.get("assertions_json"), list) else []
        covered: set[str] = set()
        for assertion in assertions:
            if not isinstance(assertion, dict):
                continue
            assertion_type = str(assertion.get("type") or "").strip()
            operator = str(assertion.get("operator") or "").strip()
            path = str(assertion.get("path") or "").strip()

            if assertion_type == "status_code":
                covered.add("status")
                continue
            if assertion_type == "response_time":
                covered.add("latency")
                continue
            if assertion_type == "schema" or operator in {"schema", "matches_schema"}:
                covered.add("schema")
                continue
            if assertion_type == "json_path":
                if path in _BUSINESS_CODE_PATHS:
                    covered.add("business_code")
                else:
                    covered.add("body_field")
        return covered

    def _dimension_label(self, dimension: str) -> str:
        return _DIMENSION_LABELS.get(dimension, dimension)
