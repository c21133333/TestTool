from __future__ import annotations

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
