from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def prepare_runtime_env() -> Path:
    sandbox_dir = Path(tempfile.mkdtemp(prefix="eazytest-ci-smoke-"))
    os.environ["EAZYTEST_DEPLOYMENT_ENV"] = "development"
    os.environ["EAZYTEST_DATABASE_URL"] = f"sqlite:///{(sandbox_dir / 'ci_smoke.db').as_posix()}"
    os.environ["EAZYTEST_DATABASE_AUTO_MIGRATE"] = "true"
    os.environ["EAZYTEST_REPORT_DIR"] = str((sandbox_dir / "reports").resolve())
    os.environ["EAZYTEST_BOOTSTRAP_ADMIN_ENABLED"] = "false"
    return sandbox_dir


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    sandbox_dir = prepare_runtime_env()

    from fastapi.testclient import TestClient

    from backend.app.main import create_application
    from backend.app.worker import run_once

    with TestClient(create_application()) as client:
        health_response = client.get("/api/v1/health")
        assert health_response.status_code == 200, health_response.text

    run_once()
    print(f"Smoke startup completed with sandbox: {sandbox_dir}")
    return 0


if __name__ == "__main__":
  raise SystemExit(main())
