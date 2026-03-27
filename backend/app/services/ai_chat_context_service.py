from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models.api_case import ApiCase
from backend.app.models.environment import Environment
from backend.app.models.execution import Execution
from backend.app.models.report import Report
from backend.app.models.suite import Suite
from backend.app.services.ai_product_knowledge_service import AiProductKnowledgeService
from backend.app.services.workspace_service import WorkspaceService


class AiChatContextService:
    _VISIBLE_SUITE_LIMIT = 12
    _CASE_SAMPLE_LIMIT = 24
    _CASE_SAMPLE_PER_SUITE = 3
    _ENVIRONMENT_SAMPLE_LIMIT = 12
    _EXECUTION_SAMPLE_LIMIT = 6
    _REPORT_SAMPLE_LIMIT = 6

    _SENSITIVE_MARKERS = (
        "authorization",
        "cookie",
        "password",
        "secret",
        "token",
        "api_key",
        "access_key",
        "refresh_key",
        "private_key",
    )

    def __init__(self, session: Session) -> None:
        self._session = session
        self._workspace = WorkspaceService(session)
        self._product_knowledge = AiProductKnowledgeService()

    def build_project_snapshot(self, project_id: int | None) -> dict[str, Any]:
        if project_id is None:
            return {
                "scope": "global",
                "summary": "No project is currently selected. The assistant can still explain product capabilities and workflow, but cannot cite project-specific assets.",
                "project": None,
                "product_knowledge": self._product_knowledge.build_snapshot(),
                "warnings": [
                    "No project is selected, so project-specific facts are unavailable.",
                ],
                "redaction_applied": True,
            }

        project = self._workspace.get_project(project_id)
        suites = self._session.query(Suite).filter(Suite.project_id == project_id).order_by(Suite.id.asc()).all()
        suite_ids = [suite.id for suite in suites]
        suite_case_counts = self._build_suite_case_counts(suite_ids)
        cases = self._build_case_samples(suites)
        environments = (
            self._session.query(Environment)
            .filter(Environment.project_id == project_id)
            .order_by(Environment.id.asc())
            .limit(self._ENVIRONMENT_SAMPLE_LIMIT)
            .all()
        )
        executions = (
            self._session.query(Execution)
            .filter(Execution.project_id == project_id)
            .order_by(Execution.created_at.desc())
            .limit(self._EXECUTION_SAMPLE_LIMIT)
            .all()
        )
        reports = (
            self._session.query(Report)
            .join(Execution, Report.execution_id == Execution.id)
            .filter(Execution.project_id == project_id)
            .order_by(Report.created_at.desc())
            .limit(self._REPORT_SAMPLE_LIMIT)
            .all()
        )

        suite_name_by_id = {suite.id: suite.name for suite in suites}
        execution_by_id = {execution.id: execution for execution in executions}
        total_case_count = sum(suite_case_counts.values())

        return {
            "scope": "project",
            "summary": (
                f"Project `{project.name}` currently contains {len(suites)} suites, "
                f"{total_case_count} cases, and {len(environments)} environments."
            ),
            "project": {
                "id": project.id,
                "name": project.name,
                "description": project.description,
            },
            "product_knowledge": self._product_knowledge.build_snapshot(),
            "suites": [
                {
                    "id": suite.id,
                    "name": suite.name,
                    "description": suite.description,
                    "case_count": suite_case_counts.get(suite.id, 0),
                }
                for suite in suites[:self._VISIBLE_SUITE_LIMIT]
            ],
            "cases": [
                {
                    "id": api_case.id,
                    "suite_id": api_case.suite_id,
                    "suite_name": suite_name_by_id.get(api_case.suite_id, ""),
                    "name": api_case.name,
                    "method": api_case.method,
                    "url": api_case.url,
                    "description": api_case.description,
                    "assertion_count": len(api_case.assertions_json or []),
                    "metadata": self._redact_payload(api_case.metadata_json),
                }
                for api_case in cases
            ],
            "environments": [
                {
                    "id": environment.id,
                    "name": environment.name,
                    "base_url": environment.base_url,
                    "description": environment.description,
                    "headers": self._redact_payload(environment.headers_json),
                    "variables": self._redact_payload(environment.variables_json),
                }
                for environment in environments
            ],
            "recent_executions": [
                {
                    "id": execution.id,
                    "suite_id": execution.suite_id,
                    "scope": execution.scope.value,
                    "status": execution.status.value,
                    "target_name": execution.target_name,
                    "summary": self._redact_payload(execution.summary_json),
                    "error_message": execution.error_message,
                    "started_at": self._format_datetime(execution.started_at),
                    "finished_at": self._format_datetime(execution.finished_at),
                    "created_at": self._format_datetime(execution.created_at),
                    "failed_items": [
                        {
                            "case_name": item.case_name,
                            "status": item.status,
                            "failure_message": item.failure_message,
                        }
                        for item in execution.items[:4]
                        if item.status != "PASS"
                    ],
                }
                for execution in executions
            ],
            "recent_reports": [
                {
                    "id": report.id,
                    "execution_id": report.execution_id,
                    "execution_target": execution_by_id.get(report.execution_id).target_name if execution_by_id.get(report.execution_id) else "",
                    "report_type": report.report_type,
                    "created_at": self._format_datetime(report.created_at),
                    "metadata": self._redact_payload(report.metadata_json),
                }
                for report in reports
            ],
            "warnings": [
                "Chat context contains a read-only business snapshot for the current project.",
                "Case details are sampled for context; suite case_count is the source of truth for totals.",
                "Sensitive fields are redacted before any AI-visible context is built.",
            ],
            "redaction_applied": True,
        }

    def _build_suite_case_counts(self, suite_ids: list[int]) -> dict[int, int]:
        if not suite_ids:
            return {}
        rows = (
            self._session.query(ApiCase.suite_id, func.count(ApiCase.id))
            .filter(ApiCase.suite_id.in_(suite_ids))
            .group_by(ApiCase.suite_id)
            .all()
        )
        return {int(suite_id): int(case_count) for suite_id, case_count in rows}

    def _build_case_samples(self, suites: list[Suite]) -> list[ApiCase]:
        visible_suites = suites[:self._VISIBLE_SUITE_LIMIT]
        visible_suite_ids = [suite.id for suite in visible_suites]
        if not visible_suite_ids:
            return []

        cases = (
            self._session.query(ApiCase)
            .filter(ApiCase.suite_id.in_(visible_suite_ids))
            .order_by(ApiCase.suite_id.asc(), ApiCase.id.asc())
            .all()
        )
        cases_by_suite_id: dict[int, list[ApiCase]] = defaultdict(list)
        for api_case in cases:
            cases_by_suite_id[api_case.suite_id].append(api_case)

        samples: list[ApiCase] = []
        sampled_case_ids: set[int] = set()
        for suite in visible_suites:
            for api_case in cases_by_suite_id.get(suite.id, [])[:self._CASE_SAMPLE_PER_SUITE]:
                samples.append(api_case)
                sampled_case_ids.add(api_case.id)
                if len(samples) >= self._CASE_SAMPLE_LIMIT:
                    return samples

        for api_case in cases:
            if api_case.id in sampled_case_ids:
                continue
            samples.append(api_case)
            if len(samples) >= self._CASE_SAMPLE_LIMIT:
                break
        return samples

    def _redact_payload(self, payload: Any) -> Any:
        if isinstance(payload, dict):
            sanitized: dict[str, Any] = {}
            for key, value in payload.items():
                if self._is_sensitive_key(key):
                    sanitized[key] = "[redacted]"
                    continue
                sanitized[str(key)] = self._redact_payload(value)
            return sanitized
        if isinstance(payload, list):
            return [self._redact_payload(item) for item in payload[:12]]
        if isinstance(payload, str) and len(payload) > 500:
            return f"{payload[:500]}..."
        return payload

    def _is_sensitive_key(self, key: str) -> bool:
        lowered = key.lower()
        return any(marker in lowered for marker in self._SENSITIVE_MARKERS)

    def _format_datetime(self, value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None
