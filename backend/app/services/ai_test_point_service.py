from __future__ import annotations

from backend.app.schemas.ai_copilot import AiTestPointRead, AiTestPointResult
from backend.app.services.markdown_endpoint_parser import MarkdownEndpointParser

_POINT_CATEGORIES = ("happy_path", "negative_path", "boundary_path")


class AiTestPointService:
    def __init__(self, session, *, parser: MarkdownEndpointParser | None = None) -> None:
        self._parser = parser or MarkdownEndpointParser()

    def generate_preview(self, context: dict) -> dict:
        markdown_text = str(context.get("markdown_text") or "").strip()
        input_snapshot = context.get("input_snapshot") if isinstance(context.get("input_snapshot"), dict) else {}

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
                    )
                )

        return {
            "result": AiTestPointResult(test_points=test_points).model_dump(),
            "warnings": warnings,
        }

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

    def _reason_for_point(self, method: str, path: str, category: str, endpoint_exists: bool) -> str:
        if endpoint_exists:
            return f"{method} {path} should be reviewed for {category} coverage against existing cases."
        return f"{method} {path} appears in the provided spec and should add {category} coverage."
