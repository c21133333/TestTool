from __future__ import annotations

import time

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal, bootstrap_database
from backend.app.core.observability import configure_logging, get_logger, log_event
from backend.app.services.auth_service import AuthService
from backend.app.services.schedule_dispatch_service import ScheduleDispatchService

logger = get_logger("scheduler")


def run_once() -> int:
    configure_logging(component="scheduler")
    settings.validate_runtime_requirements("scheduler")
    session = SessionLocal()
    try:
        runs = ScheduleDispatchService(session).dispatch_due_jobs()
        if runs:
            log_event(
                logger,
                "scheduler.dispatch.completed",
                dispatched_count=len(runs),
                run_ids=[run.id for run in runs],
            )
        return len(runs)
    finally:
        session.close()


def main() -> int:
    configure_logging(component="scheduler")
    settings.validate_runtime_requirements("scheduler")
    bootstrap_database()
    session = SessionLocal()
    try:
        AuthService(session).ensure_bootstrap_admin()
    finally:
        session.close()

    log_event(
        logger,
        "scheduler.started",
        deployment_env=settings.deployment_env,
        poll_interval_seconds=settings.scheduler_poll_interval_seconds,
        batch_size=settings.scheduler_batch_size,
    )
    while True:
        dispatched_count = run_once()
        if dispatched_count == 0:
            time.sleep(settings.scheduler_poll_interval_seconds)
