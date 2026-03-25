from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.api_case import ApiCase
from backend.app.models.environment import Environment
from backend.app.models.execution import Execution
from backend.app.models.project import Project
from backend.app.models.report import Report
from backend.app.models.suite import Suite
from backend.app.services.workspace_service import WorkspaceService


class AiChatContextService:
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

    def build_project_snapshot(self, project_id: int | None) -> dict[str, Any]:
        if project_id is None:
            return {
                "scope": "global",
                "summary": "当前未绑定项目上下文，仅能回答通用产品与流程问题。",
                "project": None,
                "warnings": ["当前未选择项目，回答将无法引用具体项目资产。"],
                "redaction_applied": True,
            }

        project = self._workspace.get_project(project_id)
        suites = self._session.query(Suite).filter(Suite.project_id == project_id).order_by(Suite.id.asc()).all()
        suite_ids = [suite.id for suite in suites]
        cases = (
            self._session.query(ApiCase)
            .filter(ApiCase.suite_id.in_(suite_ids) if suite_ids else False)
            .order_by(ApiCase.id.asc())
            .limit(24)
            .all()
        )
        environments = (
            self._session.query(Environment)
            .filter(Environment.project_id == project_id)
            .order_by(Environment.id.asc())
            .limit(12)
            .all()
        )
        executions = (
            self._session.query(Execution)
            .filter(Execution.project_id == project_id)
            .order_by(Execution.created_at.desc())
            .limit(6)
            .all()
        )
        reports = (
            self._session.query(Report)
            .join(Execution, Report.execution_id == Execution.id)
            .filter(Execution.project_id == project_id)
            .order_by(Report.created_at.desc())
            .limit(6)
            .all()
        )

        suite_name_by_id = {suite.id: suite.name for suite in suites}
        execution_by_id = {execution.id: execution for execution in executions}

        return {
            "scope": "project",
            "summary": f"当前项目 `{project.name}` 共包含 {len(suites)} 个套件、{len(cases)} 个采样用例、{len(environments)} 个环境。",
            "project": {
                "id": project.id,
                "name": project.name,
                "description": project.description,
            },
            "suites": [
                {
                    "id": suite.id,
                    "name": suite.name,
                    "description": suite.description,
                    "case_count": sum(1 for api_case in cases if api_case.suite_id == suite.id),
                }
                for suite in suites[:12]
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
                "聊天上下文仅包含当前项目的业务快照。",
                "敏感字段已脱敏，系统表与认证数据不会提供给模型。",
            ],
            "redaction_applied": True,
        }

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
