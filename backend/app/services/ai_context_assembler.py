from __future__ import annotations

from collections import Counter
import re
from typing import Any
from urllib.parse import parse_qsl, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.api_case import ApiCase
from backend.app.models.execution import Execution, ExecutionItem
from backend.app.models.report import Report
from backend.app.services.execution_service import ExecutionService
from backend.app.services.report_service import ReportService
from backend.app.services.workspace_service import WorkspaceService


class AiContextAssembler:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._execution_service = ExecutionService(session)
        self._report_service = ReportService(session)
        self._workspace_service = WorkspaceService(session)

    def build_context(self, *, capability: str, target_type: str, target_id: int) -> dict[str, Any]:
        if target_type == "project":
            input_snapshot = self.build_project_context(target_id)
        elif target_type == "suite":
            input_snapshot = self.build_suite_context(target_id)
        elif target_type == "execution":
            input_snapshot = self.build_execution_context(target_id)
        elif target_type == "report":
            input_snapshot = self.build_report_context(target_id)
        elif target_type == "case":
            input_snapshot = self.build_case_context(target_id)
        else:
            input_snapshot = {}
        return {
            "capability": capability,
            "target_type": target_type,
            "target_id": target_id,
            "input_snapshot": input_snapshot,
        }

    def build_project_context(self, project_id: int) -> dict[str, Any]:
        project = self._workspace_service.get_project(project_id)
        suites = sorted(project.suites, key=lambda current: (current.name, current.id))
        cases = [api_case for suite in suites for api_case in suite.cases]
        return {
            "project_id": project.id,
            "name": project.name,
            "description": project.description,
            "suite_count": len(suites),
            "environment_count": len(project.environments),
            "suites": [
                {
                    "suite_id": suite.id,
                    "name": suite.name,
                    "case_count": len(suite.cases),
                }
                for suite in suites
            ],
            "case_summary": self._build_case_summary(cases),
            "recent_execution": self._build_recent_execution_summary(project_id=project.id),
            "recent_report": self._build_recent_report_summary(project_id=project.id),
        }

    def build_suite_context(self, suite_id: int) -> dict[str, Any]:
        suite = self._workspace_service.get_suite(suite_id)
        cases = sorted(suite.cases, key=lambda current: (current.method, current.url, current.id))
        return {
            "suite_id": suite.id,
            "project_id": suite.project_id,
            "project_name": suite.project.name if suite.project is not None else "",
            "name": suite.name,
            "description": suite.description,
            "cases": [self._build_case_design_snapshot(api_case) for api_case in cases],
            "case_summary": self._build_case_summary(cases),
            "recent_execution": self._build_recent_execution_summary(suite_id=suite.id),
            "recent_report": self._build_recent_report_summary(suite_id=suite.id),
        }

    def build_execution_context(self, execution_id: int) -> dict[str, Any]:
        execution = self._execution_service.get_execution(execution_id)
        summary = execution.summary_json if isinstance(execution.summary_json, dict) else {}
        first_failure = summary.get("first_failure") if isinstance(summary.get("first_failure"), dict) else {}
        retry_history: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        for item in sorted(execution.items, key=lambda current: current.order_index):
            response_json = item.response_json if isinstance(item.response_json, dict) else {}
            execution_meta = response_json.get("execution_meta") if isinstance(response_json.get("execution_meta"), dict) else {}
            if not retry_history and isinstance(execution_meta.get("retry_history"), list):
                retry_history = [self._sanitize_value(entry) for entry in execution_meta.get("retry_history") if isinstance(entry, dict)]
            items.append(
                {
                    "execution_item_id": item.id,
                    "case_id": item.case_id,
                    "case_name": item.case_name,
                    "status": item.status,
                    "failure_message": item.failure_message,
                    "request": self._sanitize_value(item.request_json if isinstance(item.request_json, dict) else {}),
                    "response": self._sanitize_value(response_json),
                    "assertion_results": self._sanitize_value(item.assertion_results_json if isinstance(item.assertion_results_json, list) else []),
                }
            )
        return {
            "execution_id": execution.id,
            "status": execution.status.value,
            "target_name": execution.target_name,
            "summary": summary,
            "first_failure": first_failure,
            "retry_history": retry_history,
            "error_message": execution.error_message,
            "items": items,
        }

    def build_report_context(self, report_id: int) -> dict[str, Any]:
        report = self._report_service.get_report(report_id)
        metadata = report.metadata_json if isinstance(report.metadata_json, dict) else {}
        execution_summary = report.execution.summary_json if report.execution is not None and isinstance(report.execution.summary_json, dict) else {}
        recent_suite_execution = self._build_recent_suite_execution(report)
        return {
            "report_id": report.id,
            "execution_id": report.execution_id,
            "report_type": report.report_type,
            "metadata": metadata,
            "execution_summary": execution_summary,
            "recent_suite_execution": recent_suite_execution,
        }

    def build_case_context(self, case_id: int) -> dict[str, Any]:
        api_case = self._workspace_service.get_case(case_id)
        suite = api_case.suite
        project = suite.project if suite is not None else None
        environments = sorted(project.environments if project is not None else [], key=lambda current: (current.name, current.id))
        headers_json = self._sanitize_value(api_case.headers_json if isinstance(api_case.headers_json, dict) else {})
        body_json = self._sanitize_value(api_case.body_json)
        assertions_json = self._sanitize_value(api_case.assertions_json if isinstance(api_case.assertions_json, list) else [])
        metadata_json = self._sanitize_value(api_case.metadata_json if isinstance(api_case.metadata_json, dict) else {})
        recent_success_sample = self._build_recent_execution_sample(case_id, status="PASS")
        recent_failure_sample = self._build_recent_execution_sample(case_id, status="FAIL")
        request_shape = self._build_request_shape(url=api_case.url, body_json=body_json)
        response_shape = self._build_response_shape(recent_success_sample, recent_failure_sample)
        return {
            "case_id": api_case.id,
            "suite_id": api_case.suite_id,
            "project_id": suite.project_id if suite is not None else None,
            "project_name": project.name if project is not None else "",
            "suite_name": suite.name if suite is not None else "",
            "name": api_case.name,
            "method": api_case.method,
            "url": api_case.url,
            "headers_json": headers_json,
            "body_json": body_json,
            "assertions_json": assertions_json,
            "metadata_json": metadata_json,
            "environments": [
                {
                    "environment_id": environment.id,
                    "name": environment.name,
                    "base_url": environment.base_url,
                    "variables_json": self._sanitize_value(environment.variables_json if isinstance(environment.variables_json, dict) else {}),
                }
                for environment in environments
            ],
            "request_shape": request_shape,
            "response_shape": response_shape,
            "recent_success_sample": recent_success_sample,
            "recent_failure_sample": recent_failure_sample,
        }

    def _build_case_design_snapshot(self, api_case: ApiCase) -> dict[str, Any]:
        return {
            "case_id": api_case.id,
            "name": api_case.name,
            "method": api_case.method,
            "url": api_case.url,
            "description": api_case.description,
            "headers_json": self._sanitize_value(api_case.headers_json if isinstance(api_case.headers_json, dict) else {}),
            "body_json": self._sanitize_value(api_case.body_json),
            "assertions_json": self._sanitize_value(api_case.assertions_json if isinstance(api_case.assertions_json, list) else []),
            "metadata_json": self._sanitize_value(api_case.metadata_json if isinstance(api_case.metadata_json, dict) else {}),
        }

    def _build_case_summary(self, cases: list[ApiCase]) -> dict[str, Any]:
        endpoint_pairs = sorted({(api_case.method, api_case.url) for api_case in cases})
        assertion_type_counts: Counter[str] = Counter()
        category_counts: Counter[str] = Counter()
        priority_counts: Counter[str] = Counter()
        tag_counts: Counter[str] = Counter()

        for api_case in cases:
            assertions = api_case.assertions_json if isinstance(api_case.assertions_json, list) else []
            for assertion in assertions:
                if not isinstance(assertion, dict):
                    continue
                assertion_type = str(assertion.get("type") or "").strip()
                if assertion_type:
                    assertion_type_counts[assertion_type] += 1

            metadata = api_case.metadata_json if isinstance(api_case.metadata_json, dict) else {}
            category = str(metadata.get("category") or "").strip()
            priority = str(metadata.get("priority") or "").strip()
            if category:
                category_counts[category] += 1
            if priority:
                priority_counts[priority] += 1

            raw_tags = metadata.get("tags")
            if isinstance(raw_tags, list):
                tags = [str(tag).strip() for tag in raw_tags if str(tag).strip()]
            elif isinstance(raw_tags, str) and raw_tags.strip():
                tags = [raw_tags.strip()]
            else:
                tags = []
            for tag in tags:
                tag_counts[tag] += 1

        return {
            "total_cases": len(cases),
            "endpoint_count": len(endpoint_pairs),
            "unique_endpoints": [{"method": method, "path": path} for method, path in endpoint_pairs],
            "assertion_type_counts": dict(sorted(assertion_type_counts.items())),
            "metadata_summary": {
                "categories": dict(sorted(category_counts.items())),
                "priorities": dict(sorted(priority_counts.items())),
                "tags": dict(sorted(tag_counts.items())),
            },
        }

    def _build_recent_suite_execution(self, report: Report) -> dict[str, Any] | None:
        if report.execution is None or report.execution.suite_id is None:
            return None
        stmt = (
            select(Execution)
            .where(Execution.suite_id == report.execution.suite_id)
            .order_by(Execution.created_at.desc(), Execution.id.desc())
        )
        execution = self._session.scalar(stmt)
        if execution is None:
            return None
        return {
            "execution_id": execution.id,
            "status": execution.status.value,
            "summary": execution.summary_json if isinstance(execution.summary_json, dict) else {},
        }

    def _build_recent_success_sample(self, case_id: int) -> dict[str, Any] | None:
        return self._build_recent_execution_sample(case_id, status="PASS")

    def _build_recent_execution_sample(self, case_id: int, *, status: str) -> dict[str, Any] | None:
        stmt = (
            select(ExecutionItem)
            .where(ExecutionItem.case_id == case_id, ExecutionItem.status == status)
            .order_by(ExecutionItem.created_at.desc(), ExecutionItem.id.desc())
        )
        item = self._session.scalar(stmt)
        if item is None:
            return None
        return {
            "execution_item_id": item.id,
            "request": self._sanitize_value(item.request_json if isinstance(item.request_json, dict) else {}),
            "response": self._sanitize_value(item.response_json if isinstance(item.response_json, dict) else {}),
            "assertion_results": self._sanitize_value(item.assertion_results_json if isinstance(item.assertion_results_json, list) else []),
            "failure_message": item.failure_message,
        }

    def _build_request_shape(self, *, url: str, body_json: Any) -> dict[str, Any]:
        parsed_url = urlparse(url)
        path_params = sorted(set(re.findall(r"\{([^{}]+)\}", parsed_url.path)))
        query_params = sorted({key for key, _ in parse_qsl(parsed_url.query, keep_blank_values=True)})
        body_field_paths = sorted(self._collect_field_paths(body_json))
        return {
            "path_params": path_params,
            "query_params": query_params,
            "body_field_paths": body_field_paths,
        }

    def _build_response_shape(
        self,
        recent_success_sample: dict[str, Any] | None,
        recent_failure_sample: dict[str, Any] | None,
    ) -> dict[str, Any]:
        status_codes: list[int] = []
        top_level_keys: set[str] = set()
        for sample in (recent_success_sample, recent_failure_sample):
            if sample is None:
                continue
            response = sample.get("response") if isinstance(sample, dict) else None
            if not isinstance(response, dict):
                continue
            status_code = response.get("status_code")
            if isinstance(status_code, int) and status_code not in status_codes:
                status_codes.append(status_code)
            payload = response.get("response_json")
            if isinstance(payload, dict):
                top_level_keys.update(str(key) for key in payload.keys())
        return {
            "status_codes": status_codes,
            "top_level_keys": sorted(top_level_keys),
            "success_sample": recent_success_sample.get("response") if isinstance(recent_success_sample, dict) else None,
            "failure_sample": recent_failure_sample.get("response") if isinstance(recent_failure_sample, dict) else None,
        }

    def _collect_field_paths(self, value: Any, *, prefix: str = "") -> list[str]:
        if isinstance(value, dict):
            paths: list[str] = []
            for key, item in value.items():
                next_prefix = f"{prefix}.{key}" if prefix else str(key)
                if isinstance(item, (dict, list)):
                    nested_paths = self._collect_field_paths(item, prefix=next_prefix)
                    if nested_paths:
                        paths.extend(nested_paths)
                    else:
                        paths.append(next_prefix)
                else:
                    paths.append(next_prefix)
            return paths
        if isinstance(value, list):
            paths: list[str] = []
            for item in value:
                if isinstance(item, (dict, list)):
                    paths.extend(self._collect_field_paths(item, prefix=prefix))
            return paths
        return [prefix] if prefix else []

    def _build_recent_execution_summary(self, *, project_id: int | None = None, suite_id: int | None = None) -> dict[str, Any] | None:
        stmt = select(Execution)
        if suite_id is not None:
            stmt = stmt.where(Execution.suite_id == suite_id)
        elif project_id is not None:
            stmt = stmt.where(Execution.project_id == project_id)
        else:
            return None
        stmt = stmt.order_by(Execution.created_at.desc(), Execution.id.desc())
        execution = self._session.scalar(stmt)
        if execution is None:
            return None
        return {
            "execution_id": execution.id,
            "status": execution.status.value,
            "target_name": execution.target_name,
            "summary": execution.summary_json if isinstance(execution.summary_json, dict) else {},
        }

    def _build_recent_report_summary(self, *, project_id: int | None = None, suite_id: int | None = None) -> dict[str, Any] | None:
        stmt = select(Report).join(Execution, Report.execution_id == Execution.id)
        if suite_id is not None:
            stmt = stmt.where(Execution.suite_id == suite_id)
        elif project_id is not None:
            stmt = stmt.where(Execution.project_id == project_id)
        else:
            return None
        stmt = stmt.order_by(Report.created_at.desc(), Report.id.desc())
        report = self._session.scalar(stmt)
        if report is None:
            return None
        return {
            "report_id": report.id,
            "execution_id": report.execution_id,
            "report_type": report.report_type,
            "metadata": report.metadata_json if isinstance(report.metadata_json, dict) else {},
        }

    def _sanitize_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for key, item in value.items():
                lowered_key = str(key).lower()
                if any(token in lowered_key for token in ("token", "password", "cookie", "authorization", "set-cookie")):
                    continue
                sanitized[str(key)] = self._sanitize_value(item)
            return sanitized
        if isinstance(value, list):
            return [self._sanitize_value(item) for item in value]
        return value
