from __future__ import annotations

from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EAZYTEST_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Eazy Test Web"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./web_eazytest.db"
    database_auto_migrate: bool = True
    auth_token_ttl_hours: int = 12
    user_password_min_length: int = 12
    bootstrap_admin_enabled: bool = False
    bootstrap_admin_username: str = ""
    bootstrap_admin_password: str = ""
    report_dir: str = "web_runs"
    report_template_path: str = "src/requesttool/shared/assets/report.html"
    worker_poll_interval_seconds: float = 2.0

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
