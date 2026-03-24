from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EAZYTEST_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="Eazy Test Web", min_length=1)
    app_version: str = Field(default="0.1.0", min_length=1)
    api_prefix: str = Field(default="/api/v1", min_length=1)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    deployment_env: Literal["development", "test", "production"] = "development"
    database_url: str = Field(default="sqlite:///./web_eazytest.db", min_length=1)
    database_auto_migrate: bool = True
    auth_token_ttl_hours: int = Field(default=12, ge=1, le=168)
    auth_max_active_tokens_per_user: int = Field(default=5, ge=1, le=20)
    user_password_min_length: int = Field(default=12, ge=12, le=128)
    execution_request_timeout_seconds: int = Field(default=20, ge=1, le=600)
    execution_retry_limit: int = Field(default=1, ge=0, le=5)
    execution_stale_timeout_seconds: int = Field(default=900, ge=30, le=86400)
    bootstrap_admin_enabled: bool = False
    bootstrap_admin_username: str = ""
    bootstrap_admin_password: str = ""
    report_dir: str = Field(default="web_runs", min_length=1)
    report_template_path: str = Field(default="src/requesttool/shared/assets/report.html", min_length=1)
    worker_poll_interval_seconds: float = Field(default=2.0, gt=0, le=3600)
    legacy_imports_enabled: bool = True
    legacy_imports_sunset_date: date | None = None

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("/"):
            raise ValueError("API prefix must start with '/'.")
        return normalized.rstrip("/") or "/"

    @field_validator("legacy_imports_sunset_date")
    @classmethod
    def validate_legacy_imports_sunset_date(cls, value: date | None) -> date | None:
        if value is None:
            return None
        if value < date(2026, 1, 1):
            raise ValueError("Legacy import sunset date must be 2026-01-01 or later.")
        return value

    @model_validator(mode="after")
    def validate_runtime_safety(self) -> "Settings":
        if self.deployment_env == "production" and self.bootstrap_admin_enabled:
            raise ValueError("Bootstrap admin is forbidden in production. Provision the first admin explicitly.")
        return self

    def validate_runtime_requirements(self, component: Literal["api", "worker", "migrate"]) -> "Settings":
        self.validate_runtime_safety()
        if component in {"api", "worker"} and not self.resolved_report_template_path.is_file():
            raise ValueError(
                f"Report template does not exist: {self.resolved_report_template_path}"
            )
        if self.deployment_env == "production" and component in {"api", "worker"}:
            if self.is_sqlite:
                raise ValueError("Production runtime cannot use SQLite. Configure PostgreSQL or another production-grade database.")
            if self.database_auto_migrate:
                raise ValueError("Production runtime must start with EAZYTEST_DATABASE_AUTO_MIGRATE=false.")
        return self

    @computed_field
    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    @computed_field
    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+psycopg://", 1)
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.database_url

    @computed_field
    @property
    def is_sqlite(self) -> bool:
        return self.sqlalchemy_database_url.startswith("sqlite")

    @computed_field
    @property
    def resolved_report_dir(self) -> Path:
        return self.project_root / self.report_dir

    @computed_field
    @property
    def resolved_report_template_path(self) -> Path:
        return self.project_root / self.report_template_path

    @computed_field
    @property
    def resolved_alembic_ini_path(self) -> Path:
        return self.project_root / "alembic.ini"

    @computed_field
    @property
    def resolved_alembic_script_location(self) -> Path:
        return self.project_root / "alembic"


settings = Settings()
