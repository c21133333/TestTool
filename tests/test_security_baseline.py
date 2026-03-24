from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import session_scope
from backend.app.main import create_application
from backend.app.models.access_token import AccessToken
from backend.app.models.base import Base
from backend.app.models.execution import ExecutionScope
from backend.app.models.registry import load_model_metadata
from backend.app.models.user import UserRole
from backend.app.schemas.workspace import ApiCaseCreate, ProjectCreate, SuiteCreate
from backend.app.services.auth_service import AuthService
from backend.app.services.execution_service import ExecutionService
from backend.app.services.workspace_service import WorkspaceService


def _make_session() -> Session:
    load_model_metadata()
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()


def test_auth_service_enforces_active_token_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _make_session()
    monkeypatch.setattr("backend.app.services.auth_service.settings.auth_max_active_tokens_per_user", 2)

    service = AuthService(session)
    user = service.create_user("owner", "Owner", "Owner#Secret2026", UserRole.admin)
    session.commit()

    first_session = service.build_session(user)
    session.commit()
    second_session = service.build_session(user)
    session.commit()
    third_session = service.build_session(user)
    session.commit()

    assert service.resolve_user(first_session.access_token) is None
    assert service.resolve_user(second_session.access_token) is not None
    assert service.resolve_user(third_session.access_token) is not None


def test_auth_service_disabling_user_revokes_all_tokens() -> None:
    session = _make_session()
    service = AuthService(session)
    admin = service.create_user("admin", "Admin", "Admin#Secret2026", UserRole.admin)
    tester = service.create_user("tester", "Tester", "Tester#Secret2026", UserRole.tester)
    session.commit()

    auth_session = service.build_session(tester)
    session.commit()

    updated_user = service.set_user_active_state(tester.id, is_active=False, actor=admin)
    session.commit()

    assert updated_user.is_active is False
    assert service.resolve_user(auth_session.access_token) is None


def test_auth_service_cannot_disable_last_active_admin() -> None:
    session = _make_session()
    service = AuthService(session)
    admin = service.create_user("solo-admin", "Solo Admin", "SoloAdmin#2026", UserRole.admin)
    session.commit()

    with pytest.raises(HTTPException) as exc_info:
        service.set_user_active_state(admin.id, is_active=False, actor=admin)

    assert exc_info.value.status_code == 400
    assert "disable" in exc_info.value.detail.lower()


def _build_api_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, sessionmaker]:
    load_model_metadata()
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    monkeypatch.setattr("backend.app.main.bootstrap_database", lambda: None)
    monkeypatch.setattr("backend.app.main.SessionLocal", testing_session_local)

    app = create_application()

    def override_session_scope() -> Generator[Session, None, None]:
        session = testing_session_local()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[session_scope] = override_session_scope
    client = TestClient(app)
    return client, testing_session_local


def _issue_token(factory: sessionmaker, username: str, display_name: str, password: str, role: UserRole) -> tuple[int, str]:
    with factory() as session:
        auth_service = AuthService(session)
        user = auth_service.create_user(username, display_name, password, role)
        session.commit()
        auth_session = auth_service.build_session(user)
        session.commit()
        return user.id, auth_session.access_token


def _seed_case(factory: sessionmaker) -> int:
    with factory() as session:
        workspace = WorkspaceService(session)
        project = workspace.create_project(ProjectCreate(name="Security", description=""))
        suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Smoke", description=""))
        case = workspace.create_case(
            ApiCaseCreate(
                suite_id=suite.id,
                name="Health",
                method="GET",
                url="/health",
            )
        )
        session.commit()
        return case.id


def test_developer_cannot_create_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    client, factory = _build_api_client(monkeypatch)
    case_id = _seed_case(factory)
    _, token = _issue_token(factory, "developer", "Developer", "Developer#Secret2026", UserRole.developer)

    with client:
        response = client.post(
            "/api/v1/executions",
            json={"scope": ExecutionScope.case.value, "target_id": case_id},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403


def test_admin_can_disable_user_and_existing_token_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    client, factory = _build_api_client(monkeypatch)
    admin_id, admin_token = _issue_token(factory, "admin1", "Admin", "Admin#Secret2026", UserRole.admin)
    tester_id, tester_token = _issue_token(factory, "tester1", "Tester", "Tester#Secret2026", UserRole.tester)

    assert admin_id != tester_id

    with client:
        disable_response = client.patch(
            f"/api/v1/users/{tester_id}/status",
            json={"is_active": False, "reason": "Offboarded"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        me_response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tester_token}"},
        )

    assert disable_response.status_code == 200
    assert disable_response.json()["data"]["is_active"] is False
    assert me_response.status_code == 401


def test_health_endpoint_exposes_dependencies_metrics_and_request_id(monkeypatch: pytest.MonkeyPatch) -> None:
    client, factory = _build_api_client(monkeypatch)
    case_id = _seed_case(factory)

    monkeypatch.setattr(
        "backend.app.services.execution_service.execute_case_payload",
        lambda payload: {
            "name": payload["name"],
            "request": payload["request"],
            "response": {"success": True, "status_code": 200, "elapsed_ms": 18, "response_json": {"ok": True}},
            "assertion_results": [],
            "result": "PASS",
        },
    )
    monkeypatch.setattr("backend.app.services.execution_service.ReportService.build_execution_report", lambda self, execution: [])

    with factory() as session:
        workspace = WorkspaceService(session)
        suite = workspace.get_suite(1)
        ExecutionService(session).run_case_now(case_id, None, None)
        ExecutionService(session).queue_suite_execution(suite.id, None, None)
        session.commit()

    with client:
        response = client.get("/api/v1/health", headers={"X-Request-ID": "health-check-001"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "health-check-001"

    payload = response.json()["data"]
    dependencies = {dependency["name"]: dependency for dependency in payload["dependencies"]}

    assert payload["status"] == "ok"
    assert payload["readiness"] is True
    assert dependencies["database"]["status"] == "ok"
    assert dependencies["report_template"]["status"] == "ok"
    assert dependencies["report_dir"]["status"] == "ok"
    assert payload["metrics"]["total_executions"] == 2
    assert payload["metrics"]["success_count"] == 1
    assert payload["metrics"]["pending_count"] == 1
    assert payload["metrics"]["failed_count"] == 0
    assert payload["metrics"]["success_rate"] == 100.0


def test_projects_list_uses_paginated_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    client, factory = _build_api_client(monkeypatch)
    _, token = _issue_token(factory, "admin-projects", "Admin", "Admin#Projects2026", UserRole.admin)

    with factory() as session:
        workspace = WorkspaceService(session)
        workspace.create_project(ProjectCreate(name="Alpha", description=""))
        workspace.create_project(ProjectCreate(name="Beta", description=""))
        session.commit()

    with client:
        response = client.get("/api/v1/projects?page=1&page_size=1", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total"] == 2
    assert payload["page"] == 1
    assert payload["page_size"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["name"] == "Alpha"


def test_authenticated_lists_accept_timezone_aware_access_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    client, factory = _build_api_client(monkeypatch)
    _, token = _issue_token(factory, "admin-aware", "Admin", "Admin#Aware2026", UserRole.admin)

    with factory() as session:
        access_token = session.query(AccessToken).one()
        access_token.expires_at = datetime.now(UTC) + timedelta(hours=1)
        session.commit()

    with client:
        response = client.get("/api/v1/projects?page=1&page_size=200", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["data"]["page_size"] == 200


def test_frontend_list_page_size_contract_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    client, factory = _build_api_client(monkeypatch)
    _, token = _issue_token(factory, "admin-pages", "Admin", "Admin#Pages2026", UserRole.admin)
    case_id = _seed_case(factory)

    with factory() as session:
        suite = WorkspaceService(session).list_suites()[0]
        ExecutionService(session).queue_suite_execution(suite.id, None, None)
        session.commit()

    headers = {"Authorization": f"Bearer {token}"}

    with client:
        projects_response = client.get("/api/v1/projects?page=1&page_size=200", headers=headers)
        suites_response = client.get("/api/v1/suites?page=1&page_size=200", headers=headers)
        cases_response = client.get("/api/v1/cases?page=1&page_size=200", headers=headers)
        environments_response = client.get("/api/v1/environments?page=1&page_size=200", headers=headers)
        executions_response = client.get("/api/v1/executions?page=1&page_size=100", headers=headers)
        reports_response = client.get("/api/v1/reports?page=1&page_size=200", headers=headers)

    assert case_id > 0
    assert projects_response.status_code == 200
    assert projects_response.json()["data"]["page_size"] == 200
    assert suites_response.status_code == 200
    assert suites_response.json()["data"]["page_size"] == 200
    assert cases_response.status_code == 200
    assert cases_response.json()["data"]["page_size"] == 200
    assert environments_response.status_code == 200
    assert environments_response.json()["data"]["page_size"] == 200
    assert executions_response.status_code == 200
    assert executions_response.json()["data"]["page_size"] == 100
    assert executions_response.json()["data"]["total"] == 1
    assert reports_response.status_code == 200
    assert reports_response.json()["data"]["page_size"] == 200


def test_api_errors_use_standardized_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _build_api_client(monkeypatch)

    with client:
        unauthorized = client.get("/api/v1/projects", headers={"X-Request-ID": "req-401"})
        invalid_payload = client.post("/api/v1/auth/login", json={"username": "owner"}, headers={"X-Request-ID": "req-422"})

    unauthorized_payload = unauthorized.json()
    validation_payload = invalid_payload.json()

    assert unauthorized.status_code == 401
    assert unauthorized_payload["success"] is False
    assert unauthorized_payload["message"] == "Authentication required."
    assert unauthorized_payload["error"]["code"] == "unauthorized"
    assert unauthorized_payload["error"]["request_id"] == "req-401"

    assert invalid_payload.status_code == 422
    assert validation_payload["success"] is False
    assert validation_payload["message"] == "Request validation failed."
    assert validation_payload["error"]["code"] == "validation_error"
    assert validation_payload["error"]["request_id"] == "req-422"
    assert validation_payload["error"]["details"]["errors"]


def test_import_policy_endpoint_exposes_legacy_bridge_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    client, factory = _build_api_client(monkeypatch)
    _, token = _issue_token(factory, "viewer", "Viewer", "Viewer#Secret2026", UserRole.developer)

    with client:
        response = client.get("/api/v1/imports/policy", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["mode"] == "migration_bridge"
    assert payload["legacy_imports_enabled"] is True
    assert payload["status"] in {"migration_only", "sunset_scheduled"}
    assert payload["capabilities"]
    assert "database-backed web model" in payload["rules"][2].lower()


def test_legacy_import_routes_return_gone_when_imports_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    client, factory = _build_api_client(monkeypatch)
    _, token = _issue_token(factory, "tester-import", "Tester", "Tester#Secret2026", UserRole.tester)
    monkeypatch.setattr("backend.app.services.compatibility_service.settings.legacy_imports_enabled", False)

    with client:
        response = client.post(
            "/api/v1/imports/legacy-project",
            data={"project_id": "1"},
            files={"file": ("project.json", b"{}", "application/json")},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 410
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["status"] == 410
    assert "no longer available" in payload["message"].lower()
