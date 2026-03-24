from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthDependencyRead(BaseModel):
    name: str
    kind: str
    status: str
    details: dict[str, Any] = Field(default_factory=dict)


class HealthMetricsRead(BaseModel):
    total_executions: int
    success_count: int
    failed_count: int
    pending_count: int
    running_count: int
    success_rate: float
    average_duration_ms: float
    stale_failure_count: int
    last_execution_at: str | None = None


class HealthRuntimeRead(BaseModel):
    deployment_env: str
    api_prefix: str
    database_backend: str
    report_dir: str
    report_template_path: str
    worker_poll_interval_seconds: float


class HealthRead(BaseModel):
    status: str
    service: str
    version: str
    checked_at: str
    readiness: bool
    dependencies: list[HealthDependencyRead]
    metrics: HealthMetricsRead
    runtime: HealthRuntimeRead
