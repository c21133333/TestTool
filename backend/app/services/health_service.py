from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.timezone import to_beijing_isoformat
from backend.app.models.execution import ExecutionStatus
from backend.app.repositories.execution_repository import ExecutionRepository
from backend.app.schemas.health import HealthDependencyRead, HealthMetricsRead, HealthRead, HealthRuntimeRead


def _utc_now() -> datetime:
    return datetime.now(UTC)


class HealthService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._executions = ExecutionRepository(session)

    def build_health_snapshot(self) -> HealthRead:
        dependencies = [
            self._check_database(),
            self._check_report_template(),
            self._check_report_dir(),
        ]
        readiness = all(dependency.status == "ok" for dependency in dependencies)
        return HealthRead(
            status="ok" if readiness else "degraded",
            service=settings.app_name,
            version=settings.app_version,
            checked_at=to_beijing_isoformat(_utc_now()),
            readiness=readiness,
            dependencies=dependencies,
            metrics=self._collect_execution_metrics(),
            runtime=HealthRuntimeRead(
                deployment_env=settings.deployment_env,
                api_prefix=settings.api_prefix,
                database_backend="sqlite" if settings.is_sqlite else "postgresql",
                report_dir=str(settings.resolved_report_dir),
                report_template_path=str(settings.resolved_report_template_path),
                worker_poll_interval_seconds=settings.worker_poll_interval_seconds,
            ),
        )

    def _check_database(self) -> HealthDependencyRead:
        try:
            self._session.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001
            return HealthDependencyRead(
                name="database",
                kind="sqlalchemy",
                status="degraded",
                details={
                    "backend": "sqlite" if settings.is_sqlite else "postgresql",
                    "message": str(exc),
                },
            )
        return HealthDependencyRead(
            name="database",
            kind="sqlalchemy",
            status="ok",
            details={"backend": "sqlite" if settings.is_sqlite else "postgresql"},
        )

    def _check_report_template(self) -> HealthDependencyRead:
        template_path = settings.resolved_report_template_path
        exists = template_path.is_file()
        return HealthDependencyRead(
            name="report_template",
            kind="filesystem",
            status="ok" if exists else "degraded",
            details={"path": str(template_path), "exists": exists},
        )

    def _check_report_dir(self) -> HealthDependencyRead:
        report_dir = settings.resolved_report_dir
        try:
            report_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001
            return HealthDependencyRead(
                name="report_dir",
                kind="filesystem",
                status="degraded",
                details={"path": str(report_dir), "message": str(exc)},
            )
        return HealthDependencyRead(
            name="report_dir",
            kind="filesystem",
            status="ok",
            details={"path": str(report_dir), "exists": report_dir.exists()},
        )

    def _collect_execution_metrics(self) -> HealthMetricsRead:
        rows = self._executions.list_metric_rows()
        counts = {status.value: 0 for status in ExecutionStatus}
        durations: list[float] = []
        stale_failure_count = 0
        last_execution_at: str | None = None

        for row in rows:
            status = str(row["status"])
            counts[status] = counts.get(status, 0) + 1
            created_at = row.get("created_at")
            if isinstance(created_at, datetime):
                created_at_text = to_beijing_isoformat(created_at)
                if last_execution_at is None or created_at_text > last_execution_at:
                    last_execution_at = created_at_text
            summary = row.get("summary")
            if not isinstance(summary, dict):
                continue
            duration_ms = summary.get("duration_ms")
            if status in {ExecutionStatus.success.value, ExecutionStatus.failed.value} and isinstance(duration_ms, (int, float)):
                durations.append(float(duration_ms))
            failure_breakdown = summary.get("failure_breakdown")
            if isinstance(failure_breakdown, dict):
                stale_failure_count += int(failure_breakdown.get("worker_stale") or 0)

        terminal_count = counts.get(ExecutionStatus.success.value, 0) + counts.get(ExecutionStatus.failed.value, 0)
        success_rate = round((counts.get(ExecutionStatus.success.value, 0) / terminal_count) * 100, 2) if terminal_count else 0.0
        average_duration_ms = round(sum(durations) / len(durations), 2) if durations else 0.0

        return HealthMetricsRead(
            total_executions=sum(counts.values()),
            success_count=counts.get(ExecutionStatus.success.value, 0),
            failed_count=counts.get(ExecutionStatus.failed.value, 0),
            pending_count=counts.get(ExecutionStatus.pending.value, 0),
            running_count=counts.get(ExecutionStatus.running.value, 0),
            success_rate=success_rate,
            average_duration_ms=average_duration_ms,
            stale_failure_count=stale_failure_count,
            last_execution_at=last_execution_at,
        )
