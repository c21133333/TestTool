from __future__ import annotations

from collections.abc import Generator

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import settings
from backend.app.models.registry import load_model_metadata


def _build_engine():
    connect_args = {}
    if settings.sqlalchemy_database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(settings.sqlalchemy_database_url, future=True, connect_args=connect_args)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def bootstrap_database() -> None:
    load_model_metadata()
    if not settings.database_auto_migrate:
        return
    run_migrations()


def run_migrations(revision: str = "head") -> None:
    alembic_config = Config(str(settings.resolved_alembic_ini_path))
    alembic_config.set_main_option("script_location", str(settings.resolved_alembic_script_location))
    alembic_config.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_url)
    command.upgrade(alembic_config, revision)


def session_scope() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
