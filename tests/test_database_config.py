from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings
from backend.app.core.database import bootstrap_database


def test_settings_normalize_postgres_urls():
    assert (
        Settings(database_url="postgres://user:pass@localhost:5432/eazytest").sqlalchemy_database_url
        == "postgresql+psycopg://user:pass@localhost:5432/eazytest"
    )
    assert (
        Settings(database_url="postgresql://user:pass@localhost:5432/eazytest").sqlalchemy_database_url
        == "postgresql+psycopg://user:pass@localhost:5432/eazytest"
    )


def test_settings_keep_sqlite_url_unchanged():
    assert Settings(database_url="sqlite:///./web_eazytest.db").sqlalchemy_database_url == "sqlite:///./web_eazytest.db"


def test_bootstrap_database_skips_auto_migrate_when_disabled(monkeypatch):
    migration_calls: list[str] = []

    monkeypatch.setattr("backend.app.core.database.load_model_metadata", lambda: None)
    monkeypatch.setattr("backend.app.core.database.run_migrations", lambda revision="head": migration_calls.append(revision))
    monkeypatch.setattr("backend.app.core.database.settings.database_auto_migrate", False)

    bootstrap_database()

    assert migration_calls == []


def test_bootstrap_admin_is_disabled_by_default():
    settings = Settings()

    assert settings.bootstrap_admin_enabled is False
    assert settings.bootstrap_admin_username == ""
    assert settings.bootstrap_admin_password == ""
    assert settings.deployment_env == "development"
    assert settings.log_level == "INFO"
    assert settings.auth_max_active_tokens_per_user == 5
    assert settings.execution_request_timeout_seconds == 20
    assert settings.execution_retry_limit == 1
    assert settings.execution_stale_timeout_seconds == 900
    assert settings.legacy_imports_enabled is True
    assert settings.legacy_imports_sunset_date is None


def test_settings_reject_bootstrap_admin_in_production():
    with pytest.raises(ValidationError):
        Settings(
            deployment_env="production",
            bootstrap_admin_enabled=True,
            bootstrap_admin_username="ops-admin",
            bootstrap_admin_password="OpsAdmin#2026",
        )


def test_settings_normalize_api_prefix():
    settings = Settings(api_prefix="/api/v1/")

    assert settings.api_prefix == "/api/v1"


def test_settings_accept_legacy_import_sunset_date():
    settings = Settings(legacy_imports_sunset_date=date(2026, 12, 31))

    assert settings.legacy_imports_sunset_date == date(2026, 12, 31)


def test_settings_reject_legacy_import_sunset_date_before_2026():
    with pytest.raises(ValidationError):
        Settings(legacy_imports_sunset_date=date(2025, 12, 31))


def test_runtime_requirements_reject_sqlite_in_production():
    settings = Settings(
        deployment_env="production",
        database_url="sqlite:///./prod.db",
        database_auto_migrate=False,
    )

    with pytest.raises(ValueError, match="SQLite"):
        settings.validate_runtime_requirements("api")


def test_runtime_requirements_reject_auto_migrate_in_production():
    settings = Settings(
        deployment_env="production",
        database_url="postgresql://user:pass@localhost:5432/eazytest",
        database_auto_migrate=True,
    )

    with pytest.raises(ValueError, match="AUTO_MIGRATE=false"):
        settings.validate_runtime_requirements("worker")


def test_runtime_requirements_reject_missing_report_template():
    settings = Settings(report_template_path="missing/report-template.html")

    with pytest.raises(ValueError, match="Report template does not exist"):
        settings.validate_runtime_requirements("api")


def test_worker_run_once_uses_runtime_validation(monkeypatch):
    validation_calls: list[str] = []

    class _FakeSettings:
        def validate_runtime_requirements(self, component: str) -> None:
            validation_calls.append(component)

    class _FakeSession:
        def close(self) -> None:
            return None

    class _FakeExecutionService:
        def __init__(self, session) -> None:
            self._session = session

        def process_next_pending_execution(self):
            return None

    monkeypatch.setattr("backend.app.worker.settings", _FakeSettings())
    monkeypatch.setattr("backend.app.worker.SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr("backend.app.worker.ExecutionService", _FakeExecutionService)

    from backend.app.worker import run_once

    assert run_once() is False
    assert validation_calls == ["worker"]
