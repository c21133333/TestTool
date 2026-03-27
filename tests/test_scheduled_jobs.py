from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import session_scope
from backend.app.main import create_application
from backend.app.models.audit_log import AuditLog
from backend.app.models.base import Base
from backend.app.models.execution import Execution, ExecutionStatus, ExecutionTriggerSource
from backend.app.models.registry import load_model_metadata
from backend.app.models.scheduled_job import ScheduledJobConcurrencyPolicy, ScheduledJobMisfirePolicy, ScheduledJobRunStatus
from backend.app.models.user import UserRole
from backend.app.schemas.scheduled_job import ScheduledJobCreate
from backend.app.schemas.workspace import EnvironmentCreate, ProjectCreate, SuiteCreate
from backend.app.services.auth_service import AuthService
from backend.app.services.schedule_dispatch_service import ScheduleDispatchService
from backend.app.services.scheduled_job_service import ScheduledJobService
from backend.app.services.workspace_service import WorkspaceService


def _make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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

    def override_session_scope():
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
    return TestClient(app), testing_session_local


def _issue_token(factory: sessionmaker, username: str, role: UserRole) -> str:
    with factory() as session:
        auth_service = AuthService(session)
        user = auth_service.create_user(username, username, "Schedule#Secret2026", role)
        session.commit()
        auth_session = auth_service.build_session(user)
        session.commit()
        return auth_session.access_token


def test_create_scheduled_job_computes_next_run_at(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _make_session()
    workspace = WorkspaceService(session)
    actor = AuthService(session).create_user("job_owner", "Job Owner", "Owner#Secret2026", UserRole.admin)
    project = workspace.create_project(ProjectCreate(name="Schedule Project", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Smoke Suite", description=""))
    environment = workspace.create_environment(
        EnvironmentCreate(project_id=project.id, name="staging", base_url="https://example.com")
    )
    session.commit()

    fixed_now = datetime(2026, 3, 27, 0, 15, tzinfo=UTC)
    monkeypatch.setattr("backend.app.services.scheduled_job_service._utc_now", lambda: fixed_now)

    payload = ScheduledJobCreate(
        project_id=project.id,
        suite_id=suite.id,
        environment_id=environment.id,
        name="daily smoke",
        description="weekday smoke run",
        cron_expr="0 9 * * 1-5",
        timezone="Asia/Shanghai",
        enabled=True,
        concurrency_policy=ScheduledJobConcurrencyPolicy.forbid,
        misfire_policy=ScheduledJobMisfirePolicy.skip,
    )

    job = ScheduledJobService(session).create_job(payload, actor=actor)

    assert job.next_run_at == datetime(2026, 3, 27, 1, 0, tzinfo=UTC)


def test_create_scheduled_job_rejects_cross_project_environment() -> None:
    session = _make_session()
    workspace = WorkspaceService(session)
    actor = AuthService(session).create_user("job_admin", "Job Admin", "Admin#Secret2026", UserRole.admin)
    primary_project = workspace.create_project(ProjectCreate(name="Primary Project", description=""))
    secondary_project = workspace.create_project(ProjectCreate(name="Secondary Project", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=primary_project.id, name="Primary Suite", description=""))
    foreign_environment = workspace.create_environment(
        EnvironmentCreate(project_id=secondary_project.id, name="foreign", base_url="https://foreign.example.com")
    )
    session.commit()

    payload = ScheduledJobCreate(
        project_id=primary_project.id,
        suite_id=suite.id,
        environment_id=foreign_environment.id,
        name="invalid schedule",
        description="should fail",
        cron_expr="0 9 * * 1-5",
        timezone="Asia/Shanghai",
        enabled=True,
        concurrency_policy=ScheduledJobConcurrencyPolicy.forbid,
        misfire_policy=ScheduledJobMisfirePolicy.skip,
    )

    with pytest.raises(HTTPException):
        ScheduledJobService(session).create_job(payload, actor=actor)


def test_scheduled_jobs_route_create_and_list(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_now = datetime(2026, 3, 27, 0, 15, tzinfo=UTC)
    monkeypatch.setattr("backend.app.services.scheduled_job_service._utc_now", lambda: fixed_now)
    client, factory = _build_api_client(monkeypatch)
    token = _issue_token(factory, "schedule-admin", UserRole.admin)
    headers = {"Authorization": f"Bearer {token}"}

    with factory() as session:
        workspace = WorkspaceService(session)
        project = workspace.create_project(ProjectCreate(name="API Schedule Project", description=""))
        suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="API Suite", description=""))
        environment = workspace.create_environment(
            EnvironmentCreate(project_id=project.id, name="api-env", base_url="https://example.com")
        )
        session.commit()
        project_id = project.id
        suite_id = suite.id
        environment_id = environment.id

    payload = {
        "project_id": project_id,
        "suite_id": suite_id,
        "environment_id": environment_id,
        "name": "daily smoke",
        "description": "weekday smoke run",
        "cron_expr": "0 9 * * 1-5",
        "timezone": "Asia/Shanghai",
        "enabled": True,
        "concurrency_policy": "forbid",
        "misfire_policy": "skip",
    }

    with client:
        created = client.post("/api/v1/scheduled-jobs", json=payload, headers=headers)
        listed = client.get("/api/v1/scheduled-jobs", headers=headers)

    assert created.status_code == 200
    created_payload = created.json()["data"]
    assert created_payload["name"] == "daily smoke"
    assert created_payload["suite_id"] == suite_id
    assert created_payload["next_run_at"] == "2026-03-27T01:00:00Z"

    assert listed.status_code == 200
    listed_items = listed.json()["data"]["items"]
    assert len(listed_items) == 1
    assert listed_items[0]["name"] == "daily smoke"

    with factory() as session:
        latest_log = session.query(AuditLog).order_by(AuditLog.id.desc()).first()
        assert latest_log is not None
        assert latest_log.action == "scheduled_job.create"
        assert latest_log.resource_type == "scheduled_job"


def test_scheduled_jobs_route_forbids_developer_write(monkeypatch: pytest.MonkeyPatch) -> None:
    client, factory = _build_api_client(monkeypatch)
    token = _issue_token(factory, "schedule-dev", UserRole.developer)
    headers = {"Authorization": f"Bearer {token}"}

    with factory() as session:
        workspace = WorkspaceService(session)
        project = workspace.create_project(ProjectCreate(name="Forbidden Project", description=""))
        suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Forbidden Suite", description=""))
        environment = workspace.create_environment(
            EnvironmentCreate(project_id=project.id, name="forbidden-env", base_url="https://example.com")
        )
        session.commit()
        payload = {
            "project_id": project.id,
            "suite_id": suite.id,
            "environment_id": environment.id,
            "name": "developer schedule",
            "description": "should be forbidden",
            "cron_expr": "0 9 * * 1-5",
            "timezone": "Asia/Shanghai",
            "enabled": True,
            "concurrency_policy": "forbid",
            "misfire_policy": "skip",
        }

    with client:
        response = client.post("/api/v1/scheduled-jobs", json=payload, headers=headers)

    assert response.status_code == 403


def test_execution_route_exposes_schedule_trigger_source(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_now = datetime(2026, 3, 27, 0, 15, tzinfo=UTC)
    monkeypatch.setattr("backend.app.services.scheduled_job_service._utc_now", lambda: fixed_now)
    client, factory = _build_api_client(monkeypatch)
    token = _issue_token(factory, "schedule-trigger-admin", UserRole.admin)
    headers = {"Authorization": f"Bearer {token}"}

    with factory() as session:
        workspace = WorkspaceService(session)
        project = workspace.create_project(ProjectCreate(name="Trigger Source Project", description=""))
        suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Trigger Source Suite", description=""))
        environment = workspace.create_environment(
            EnvironmentCreate(project_id=project.id, name="trigger-env", base_url="https://example.com")
        )
        session.commit()
        payload = {
            "project_id": project.id,
            "suite_id": suite.id,
            "environment_id": environment.id,
            "name": "trigger source job",
            "description": "expose schedule source in execution payload",
            "cron_expr": "0 9 * * 1-5",
            "timezone": "Asia/Shanghai",
            "enabled": True,
            "concurrency_policy": "forbid",
            "misfire_policy": "skip",
        }

    with client:
        created = client.post("/api/v1/scheduled-jobs", json=payload, headers=headers)
        assert created.status_code == 200
        job_id = created.json()["data"]["id"]

        triggered = client.post(f"/api/v1/scheduled-jobs/{job_id}/trigger", headers=headers)
        assert triggered.status_code == 200
        execution_id = triggered.json()["data"]["execution_id"]
        assert execution_id is not None

        execution_response = client.get(f"/api/v1/executions/{execution_id}", headers=headers)

    assert execution_response.status_code == 200
    execution_payload = execution_response.json()["data"]
    assert execution_payload["trigger_source"] == "schedule"
    assert execution_payload["scheduled_job_id"] == job_id
    assert execution_payload["scheduled_run_id"] == triggered.json()["data"]["id"]


def test_scheduler_dispatch_creates_pending_suite_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _make_session()
    workspace = WorkspaceService(session)
    actor = AuthService(session).create_user("dispatch-admin", "Dispatch Admin", "Dispatch#Secret2026", UserRole.admin)
    project = workspace.create_project(ProjectCreate(name="Dispatch Project", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Dispatch Suite", description=""))
    environment = workspace.create_environment(
        EnvironmentCreate(project_id=project.id, name="dispatch-env", base_url="https://example.com")
    )
    session.commit()

    planned_run_at = datetime(2026, 3, 27, 1, 0, tzinfo=UTC)
    monkeypatch.setattr("backend.app.services.scheduled_job_service._utc_now", lambda: datetime(2026, 3, 27, 0, 15, tzinfo=UTC))
    job = ScheduledJobService(session).create_job(
        ScheduledJobCreate(
            project_id=project.id,
            suite_id=suite.id,
            environment_id=environment.id,
            name="dispatch job",
            description="dispatch due job",
            cron_expr="0 9 * * 1-5",
            timezone="Asia/Shanghai",
            enabled=True,
            concurrency_policy=ScheduledJobConcurrencyPolicy.forbid,
            misfire_policy=ScheduledJobMisfirePolicy.skip,
        ),
        actor=actor,
    )
    job.next_run_at = planned_run_at
    session.commit()

    dispatched_run = ScheduleDispatchService(session).dispatch_due_job(job.id, now=planned_run_at)
    session.refresh(job)

    assert dispatched_run.execution_id is not None
    stored_execution = session.get(Execution, dispatched_run.execution_id)
    assert stored_execution is not None
    assert stored_execution.status == ExecutionStatus.pending
    assert stored_execution.trigger_source == ExecutionTriggerSource.schedule
    assert stored_execution.scheduled_job_id == job.id
    assert stored_execution.scheduled_run_id == dispatched_run.id
    assert dispatched_run.status == ScheduledJobRunStatus.triggered
    assert job.last_triggered_execution_id == dispatched_run.execution_id
    assert job.next_run_at is not None
    assert _as_utc(job.next_run_at) > planned_run_at


def test_scheduler_forbid_policy_skips_when_previous_execution_active(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _make_session()
    workspace = WorkspaceService(session)
    actor = AuthService(session).create_user("skip-admin", "Skip Admin", "Skip#Secret2026", UserRole.admin)
    project = workspace.create_project(ProjectCreate(name="Skip Project", description=""))
    suite = workspace.create_suite(SuiteCreate(project_id=project.id, name="Skip Suite", description=""))
    environment = workspace.create_environment(
        EnvironmentCreate(project_id=project.id, name="skip-env", base_url="https://example.com")
    )
    session.commit()

    initial_now = datetime(2026, 3, 27, 0, 15, tzinfo=UTC)
    monkeypatch.setattr("backend.app.services.scheduled_job_service._utc_now", lambda: initial_now)
    job = ScheduledJobService(session).create_job(
        ScheduledJobCreate(
            project_id=project.id,
            suite_id=suite.id,
            environment_id=environment.id,
            name="skip job",
            description="skip when active execution exists",
            cron_expr="0 9 * * 1-5",
            timezone="Asia/Shanghai",
            enabled=True,
            concurrency_policy=ScheduledJobConcurrencyPolicy.forbid,
            misfire_policy=ScheduledJobMisfirePolicy.skip,
        ),
        actor=actor,
    )
    first_due_at = datetime(2026, 3, 27, 1, 0, tzinfo=UTC)
    job.next_run_at = first_due_at
    session.commit()

    first_run = ScheduleDispatchService(session).dispatch_due_job(job.id, now=first_due_at)
    assert first_run.status == ScheduledJobRunStatus.triggered

    session.refresh(job)
    second_due_at = job.next_run_at
    assert second_due_at is not None

    skipped_run = ScheduleDispatchService(session).dispatch_due_job(job.id, now=second_due_at)
    session.refresh(job)

    assert skipped_run.status == ScheduledJobRunStatus.skipped
    assert skipped_run.execution_id is None
    assert job.next_run_at is not None
    assert _as_utc(job.next_run_at) > _as_utc(second_due_at)
