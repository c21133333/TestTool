from __future__ import annotations

import time

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal, bootstrap_database
from backend.app.core.observability import configure_logging, get_logger, log_event
from backend.app.services.auth_service import AuthService
from backend.app.services.execution_service import ExecutionService

logger = get_logger("worker")


def run_once() -> bool:
    configure_logging(component="worker")
    settings.validate_runtime_requirements("worker")
    session = SessionLocal()
    try:
        execution = ExecutionService(session).process_next_pending_execution()
        if execution is not None:
            log_event(
                logger,
                "worker.execution.processed",
                execution_id=execution.id,
                scope=execution.scope,
                status=execution.status,
            )
        return execution is not None
    finally:
        session.close()


def main() -> int:
    configure_logging(component="worker")
    settings.validate_runtime_requirements("worker")
    bootstrap_database()
    session = SessionLocal()
    try:
        AuthService(session).ensure_bootstrap_admin()
    finally:
        session.close()

    log_event(
        logger,
        "worker.started",
        deployment_env=settings.deployment_env,
        poll_interval_seconds=settings.worker_poll_interval_seconds,
    )
    while True:
        processed = run_once()
        if not processed:
            time.sleep(settings.worker_poll_interval_seconds)
