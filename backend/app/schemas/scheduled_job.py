from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models.scheduled_job import (
    ScheduledJobConcurrencyPolicy,
    ScheduledJobMisfirePolicy,
    ScheduledJobRunStatus,
)


class ScheduledJobCreate(BaseModel):
    project_id: int
    suite_id: int
    environment_id: int | None = None
    name: str
    description: str = ""
    cron_expr: str
    timezone: str = "Asia/Shanghai"
    enabled: bool = True
    concurrency_policy: ScheduledJobConcurrencyPolicy = ScheduledJobConcurrencyPolicy.forbid
    misfire_policy: ScheduledJobMisfirePolicy = ScheduledJobMisfirePolicy.skip

    @field_validator("name", "description", "cron_expr", "timezone")
    @classmethod
    def strip_text_fields(cls, value: str) -> str:
        return value.strip()


class ScheduledJobUpdate(BaseModel):
    project_id: int
    suite_id: int
    environment_id: int | None = None
    name: str
    description: str = ""
    cron_expr: str
    timezone: str = "Asia/Shanghai"
    enabled: bool = True
    concurrency_policy: ScheduledJobConcurrencyPolicy = ScheduledJobConcurrencyPolicy.forbid
    misfire_policy: ScheduledJobMisfirePolicy = ScheduledJobMisfirePolicy.skip

    @field_validator("name", "description", "cron_expr", "timezone")
    @classmethod
    def strip_text_fields(cls, value: str) -> str:
        return value.strip()


class ScheduledJobRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scheduled_job_id: int
    planned_run_at: datetime
    triggered_at: datetime | None
    execution_id: int | None
    status: ScheduledJobRunStatus
    message: str
    created_at: datetime


class ScheduledJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    suite_id: int
    environment_id: int | None
    name: str
    description: str
    cron_expr: str
    timezone: str
    enabled: bool
    next_run_at: datetime | None
    last_triggered_at: datetime | None
    last_triggered_execution_id: int | None
    concurrency_policy: ScheduledJobConcurrencyPolicy
    misfire_policy: ScheduledJobMisfirePolicy
    created_by_user_id: int | None
    updated_by_user_id: int | None
    created_at: datetime
    updated_at: datetime
    runs: list[ScheduledJobRunRead] = Field(default_factory=list)


class ScheduledJobListData(BaseModel):
    items: list[ScheduledJobRead]
    total: int
    page: int
    page_size: int
