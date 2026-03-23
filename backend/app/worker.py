from __future__ import annotations

import time

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal, bootstrap_database
from backend.app.services.auth_service import AuthService
from backend.app.services.execution_service import ExecutionService


def run_once() -> bool:
    session = SessionLocal()
    try:
        execution = ExecutionService(session).process_next_pending_execution()
        return execution is not None
    finally:
        session.close()


def main() -> int:
    bootstrap_database()
    session = SessionLocal()
    try:
        AuthService(session).ensure_bootstrap_admin()
    finally:
        session.close()

    print("Eazy Test worker started.")
    while True:
        processed = run_once()
        if not processed:
            time.sleep(settings.worker_poll_interval_seconds)
