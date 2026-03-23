from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.api.dependencies.auth import require_roles
from backend.app.models import AccessToken, ApiCase, Environment, Execution, Project, Report, Suite, User
from backend.app.models.base import Base
from backend.app.models.user import UserRole
from backend.app.schemas.audit_log import AuditLogRead
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.auth_service import AuthService
from backend.app.services.execution_service import ExecutionService
from backend.app.services.import_service import ImportService
from backend.app.services.report_service import ReportService
from backend.app.services.workspace_service import WorkspaceService
from backend.app.schemas.workspace import ApiCaseCreate, EnvironmentCreate, ProjectCreate, SuiteCreate


def _make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()


def test_auth_service_creates_and_resolves_session():
    session = _make_session()
    service = AuthService(session)
    user = service.create_user("owner", "Owner", "Owner#Secret2026", UserRole.admin)
    session.commit()

    authenticated = service.authenticate("owner", "Owner#Secret2026")
    auth_session = service.build_session(authenticated)
    session.commit()

    resolved = service.resolve_user(auth_session.access_token)

    assert resolved is not None
    assert resolved.username == "owner"
    assert session.query(User).count() == 1
    assert session.query(AccessToken).count() == 1


def test_execution_service_runs_single_case(monkeypatch):
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Demo", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Smoke", description=""))
    case = workspace.create_case(
        ApiCaseCreate(
            suite_id=suite.id,
            name="Health check",
            method="GET",
            url="/health",
            assertions_json=[{"type": "status_code", "operator": "==", "expected": 200}],
        )
    )
    environment = workspace.create_environment(
        EnvironmentCreate(project_id=project.id, name="dev", base_url="https://example.com")
    )
    session.commit()

    monkeypatch.setattr(
        "backend.app.services.execution_service.execute_case_payload",
        lambda payload: {
            "name": payload["name"],
            "request": payload["request"],
            "response": {
                "success": True,
                "status_code": 200,
                "elapsed_ms": 42,
                "response_text": '{"ok": true}',
                "response_json": {"ok": True},
            },
            "assertion_results": [{"type": "status_code", "result": "PASS", "expected": 200, "actual": 200, "message": ""}],
            "result": "PASS",
        },
    )
    monkeypatch.setattr("backend.app.services.execution_service.ReportService.build_execution_report", lambda self, execution: [])

    execution = ExecutionService(session).run_case_now(case.id, environment.id, None)

    assert execution.status.value == "success"
    assert execution.summary_json["ok"] == 1
    assert len(execution.items) == 1
    assert session.query(Project).count() == 1
    assert session.query(Suite).count() == 1
    assert session.query(ApiCase).count() == 1
    assert session.query(Environment).count() == 1
    assert session.query(Execution).count() == 1


def test_workspace_service_updates_and_deletes_resources():
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Demo", description="old"))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Suite A", description="old suite"))
    environment = workspace.create_environment(
        EnvironmentCreate(project_id=project.id, name="dev", base_url="https://old.example.com")
    )
    case = workspace.create_case(
        ApiCaseCreate(
            suite_id=suite.id,
            name="Case A",
            method="GET",
            url="/old",
            assertions_json=[],
        )
    )
    session.commit()

    workspace.update_project(project.id, ProjectCreate(name="Demo V2", description="new"))
    workspace.update_suite(suite.id, SuiteCreate(project_id=project.id, name="Suite B", description="new suite"))
    workspace.update_environment(
        environment.id,
        EnvironmentCreate(project_id=project.id, name="prod", base_url="https://prod.example.com"),
    )
    workspace.update_case(
        case.id,
        ApiCaseCreate(
            suite_id=suite.id,
            name="Case B",
            method="POST",
            url="/new",
            headers_json={"X-Test": "1"},
            assertions_json=[{"type": "status_code", "operator": "==", "expected": 200}],
        ),
    )
    session.commit()

    updated_project = workspace.get_project(project.id)
    updated_suite = workspace.get_suite(suite.id)
    updated_environment = workspace.get_environment(environment.id)
    updated_case = workspace.get_case(case.id)

    assert updated_project.name == "Demo V2"
    assert updated_suite.name == "Suite B"
    assert updated_environment.base_url == "https://prod.example.com"
    assert updated_case.method == "POST"
    assert updated_case.headers_json["X-Test"] == "1"

    workspace.delete_case(case.id)
    workspace.delete_environment(environment.id)
    workspace.delete_suite(suite.id)
    session.commit()

    assert session.query(ApiCase).count() == 0
    assert session.query(Environment).count() == 0
    assert session.query(Suite).count() == 0


def test_execution_worker_processes_pending_suite(monkeypatch):
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Queue", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Queued Suite", description=""))
    workspace.create_case(
        ApiCaseCreate(
            suite_id=suite.id,
            name="Case 1",
            method="GET",
            url="/queued",
            assertions_json=[],
        )
    )
    session.commit()

    queued = ExecutionService(session).queue_suite_execution(suite.id, None, None)
    session.commit()

    monkeypatch.setattr(
        "backend.app.services.execution_service.execute_case_payload",
        lambda payload: {
            "name": payload["name"],
            "request": payload["request"],
            "response": {"success": True, "status_code": 200, "elapsed_ms": 12, "response_json": {"ok": True}},
            "assertion_results": [],
            "result": "PASS",
        },
    )
    monkeypatch.setattr("backend.app.services.execution_service.ReportService.build_execution_report", lambda self, execution: [])

    processed = ExecutionService(session).process_next_pending_execution()

    assert processed is not None
    assert processed.id == queued.id
    assert processed.status.value == "success"
    assert processed.summary_json["ok"] == 1


def test_report_service_get_report_raises_for_missing():
    session = _make_session()
    service = ReportService(session)

    try:
        service.get_report(999)
    except Exception as exc:  # noqa: BLE001
        assert "Report not found" in str(exc)
    else:
        raise AssertionError("Expected missing report to raise.")


def test_execution_service_can_cancel_pending_suite():
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Cancel", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Cancelable", description=""))
    workspace.create_case(ApiCaseCreate(suite_id=suite.id, name="Case", method="GET", url="/cancel"))
    session.commit()

    execution = ExecutionService(session).queue_suite_execution(suite.id, None, None)
    canceled = ExecutionService(session).cancel_execution(execution.id)

    assert canceled.status.value == "failed"
    assert canceled.error_message == "Canceled by user."
    assert canceled.summary_json["_control"]["canceled"] is True


def test_execution_service_can_retry_case_execution(monkeypatch):
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Retry", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Retry Suite", description=""))
    case = workspace.create_case(ApiCaseCreate(suite_id=suite.id, name="Retry Case", method="GET", url="/retry"))
    session.commit()

    monkeypatch.setattr(
        "backend.app.services.execution_service.execute_case_payload",
        lambda payload: {
            "name": payload["name"],
            "request": payload["request"],
            "response": {"success": True, "status_code": 200, "elapsed_ms": 5, "response_json": {"ok": True}},
            "assertion_results": [],
            "result": "PASS",
        },
    )
    monkeypatch.setattr("backend.app.services.execution_service.ReportService.build_execution_report", lambda self, execution: [])

    original = ExecutionService(session).run_case_now(case.id, None, None)
    retried = ExecutionService(session).retry_execution(original.id, None)

    assert original.id != retried.id
    assert retried.status.value == "success"


def test_execution_service_lists_filtered_paginated_executions(monkeypatch):
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Exec Filters", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Filter Suite", description=""))
    case = workspace.create_case(ApiCaseCreate(suite_id=suite.id, name="Case Filter", method="GET", url="/filter"))
    session.commit()

    queued_suite = ExecutionService(session).queue_suite_execution(suite.id, None, None)

    monkeypatch.setattr(
        "backend.app.services.execution_service.execute_case_payload",
        lambda payload: {
            "name": payload["name"],
            "request": payload["request"],
            "response": {"success": False, "status_code": 500, "elapsed_ms": 9, "response_json": {"ok": False}},
            "assertion_results": [{"type": "status_code", "result": "FAIL", "message": "status mismatch"}],
            "result": "FAIL",
        },
    )
    monkeypatch.setattr("backend.app.services.execution_service.ReportService.build_execution_report", lambda self, execution: [])
    failed_case = ExecutionService(session).run_case_now(case.id, None, None)

    filtered_executions, total = ExecutionService(session).list_executions(
        page=1,
        page_size=1,
        status=failed_case.status,
        scope=failed_case.scope,
        search="Case Filter",
        failed_only=True,
    )

    assert total == 1
    assert len(filtered_executions) == 1
    assert filtered_executions[0].id == failed_case.id
    assert filtered_executions[0].id != queued_suite.id


def test_audit_log_service_records_entries():
    session = _make_session()
    actor = AuthService(session).create_user("auditor", "Auditor", "Auditor#Secret2026", UserRole.admin)
    session.commit()

    record = AuditLogService(session).record(
        actor=actor,
        action="project.create",
        resource_type="project",
        resource_id=12,
        summary="Created project Demo",
        details={"name": "Demo"},
    )
    session.commit()

    logs, total = AuditLogService(session).list_logs()

    assert record.id is not None
    assert total == 1
    assert len(logs) == 1
    assert logs[0].user_id == actor.id
    assert logs[0].details_json["name"] == "Demo"
    audit_log = AuditLogRead.model_validate(logs[0])
    assert audit_log.actor_username == "auditor"
    assert audit_log.actor_display_name == "Auditor"
    assert audit_log.actor_role == "admin"


def test_audit_log_service_supports_filters_and_pagination():
    session = _make_session()
    auth_service = AuthService(session)
    admin = auth_service.create_user("admin1", "Admin", "Admin#Secret2026", UserRole.admin)
    tester = auth_service.create_user("tester2", "Tester", "Tester#Secret2026", UserRole.tester)
    session.commit()

    audit_service = AuditLogService(session)
    audit_service.record(
        actor=admin,
        action="project.create",
        resource_type="project",
        resource_id=1,
        summary="Created Alpha",
        details={"name": "Alpha"},
    )
    audit_service.record(
        actor=tester,
        action="suite.update",
        resource_type="suite",
        resource_id=2,
        summary="Updated Beta",
        details={"name": "Beta"},
    )
    session.commit()

    filtered_logs, filtered_total = audit_service.list_logs(action="suite.update", actor="tester2", page=1, page_size=1)

    assert filtered_total == 1
    assert len(filtered_logs) == 1
    assert filtered_logs[0].summary == "Updated Beta"


def test_require_roles_blocks_developer_writes():
    session = _make_session()
    developer = AuthService(session).create_user("dev1", "Developer", "Developer#Secret2026", UserRole.developer)
    tester = AuthService(session).create_user("tester1", "Tester", "Tester#Secret2026", UserRole.tester)
    session.commit()

    guard = require_roles(UserRole.admin, UserRole.tester)

    try:
        guard(current_user=developer)
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Developer should not pass write guard.")

    assert guard(current_user=tester).id == tester.id


def test_auth_service_rejects_weak_passwords():
    session = _make_session()

    try:
        AuthService(session).create_user("weak", "Weak", "secret", UserRole.tester)
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "密码" in exc.detail
    else:
        raise AssertionError("Expected weak password to be rejected.")


def test_import_service_imports_legacy_project_json(tmp_path):
    session = _make_session()
    workspace = WorkspaceService(session)
    project = workspace.create_project(ProjectCreate(name="Migrated", description=""))
    session.commit()

    run_json = tmp_path / "legacy-run.json"
    run_html = tmp_path / "legacy-run.html"
    run_json.write_text(
        json.dumps(
            {
                "suite_name": "History Suite",
                "base_url": "https://example.com",
                "execute_time": "2026-03-23T10:00:00",
                "summary": {"total": 1, "ok": 1, "ng": 0, "pass_rate": 100.0, "duration_ms": 12},
                "items": [
                    {
                        "case_id": "LEG-001",
                        "name": "Historical health",
                        "category": "history",
                        "request": {
                            "method": "GET",
                            "url": "https://example.com/history/health",
                            "headers": {"Accept": "application/json"},
                            "body": None,
                        },
                        "response": {
                            "status_code": 200,
                            "elapsed_ms": 12,
                            "response_json": {"ok": True},
                            "assertion_results": [
                                {"type": "status_code", "result": "PASS", "expected": 200, "actual": 200, "message": ""}
                            ],
                        },
                        "elapsed_ms": 12,
                        "result": "OK",
                        "failure_reason": "",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    run_html.write_text("<html><body>legacy report</body></html>", encoding="utf-8")

    legacy_payload = {
        "envs": [
            {
                "name": "desktop-dev",
                "baseUrl": "https://example.com",
                "headers": {"Authorization": "Bearer token"},
                "vars": {"tenant": "demo"},
            }
        ],
        "suites": [
            {
                "type": "folder",
                "name": "Smoke Suite",
                "data": {
                    "description": "legacy smoke",
                    "global_headers": [{"key": "X-Suite", "value": "smoke", "enabled": True}],
                    "globals": [{"key": "tenant", "value": "demo", "enabled": True}],
                },
                "children": [
                    {
                        "type": "request",
                        "name": "GET Health",
                        "path": "legacy/health.json",
                        "data": {
                            "name": "Health",
                            "method": "GET",
                            "url": "/health",
                            "params": {"verbose": True},
                            "headers": {"Accept": "application/json"},
                            "assertions": [
                                {"type": "status_code", "operator": "==", "expected": 200, "enabled": True},
                                {"type": "json_path", "path": "$.ok", "operator": "==", "expected": True, "enabled": False},
                            ],
                        },
                    },
                    {
                        "type": "folder",
                        "name": "Nested",
                        "children": [
                            {
                                "type": "request",
                                "name": "POST Login",
                                "path": "legacy/login.json",
                                "data": {
                                    "name": "Login",
                                    "method": "POST",
                                    "url": "/login",
                                    "body": {"username": "demo"},
                                    "preProcessors": [{"type": "set_variable", "config": {"key": "token", "value": "1"}, "enabled": True}],
                                },
                            }
                        ],
                    },
                ],
            }
        ],
        "runsIndex": [
            {
                "run_id": "legacy_run_001",
                "suite_name": "History Suite",
                "execute_time": "2026-03-23T10:00:00",
                "summary": {"total": 1, "ok": 1, "ng": 0, "pass_rate": 100.0, "duration_ms": 12},
                "json_path": str(run_json),
                "html_path": str(run_html),
            }
        ],
    }
    legacy_file = tmp_path / "project.json"
    legacy_file.write_text(json.dumps(legacy_payload), encoding="utf-8")

    result = ImportService(session).import_legacy_project(project.id, legacy_file)
    session.commit()

    imported_project = workspace.get_project(project.id)
    assert result["created_environments"] == 1
    assert result["created_suites"] == 1
    assert result["created_cases"] == 2
    assert result["created_executions"] == 1
    assert result["created_reports"] == 2
    assert result["skipped_runs"] == 0
    assert len(imported_project.environments) == 1
    assert len(imported_project.suites) == 2
    imported_suite = next(suite for suite in imported_project.suites if suite.name == "Smoke Suite")
    history_suite = next(suite for suite in imported_project.suites if suite.name == "History Suite")
    assert len(imported_suite.cases) == 2
    assert len(history_suite.cases) == 1

    health_case = next(case for case in imported_suite.cases if case.name == "Health")
    login_case = next(case for case in imported_suite.cases if case.name == "Login")
    historical_case = history_suite.cases[0]

    assert health_case.url.endswith("/health?verbose=True")
    assert health_case.headers_json["X-Suite"] == "smoke"
    assert health_case.headers_json["Accept"] == "application/json"
    assert len(health_case.assertions_json) == 1
    assert health_case.metadata_json["legacy_variables"]["tenant"] == "demo"
    assert login_case.metadata_json["legacy_import"]["folder_path"] == ["Nested"]
    assert len(login_case.pre_processors_json) == 1
    assert historical_case.metadata_json["source_case_id"] == "LEG-001"
    assert session.query(Execution).count() == 1
    assert session.query(Report).count() == 2
    imported_execution = session.query(Execution).one()
    assert imported_execution.target_name == "History Suite"
    assert len(imported_execution.items) == 1
    imported_report_paths = [report.file_path for report in session.query(Report).all()]
    assert all("legacy_imports" in path for path in imported_report_paths)
