from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.execution import ExecutionScope, ExecutionStatus


class ExecutionCreateRequest(BaseModel):
    scope: ExecutionScope
    target_id: int
    environment_id: int | None = None


class ExecutionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int | None
    order_index: int
    case_name: str
    status: str
    elapsed_ms: int | None
    request_json: dict[str, Any]
    response_json: dict[str, Any]
    assertion_results_json: list[dict[str, Any]]
    failure_message: str


class ExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    suite_id: int | None
    environment_id: int | None
    scope: ExecutionScope
    status: ExecutionStatus
    target_name: str
    summary_json: dict[str, Any]
    error_message: str
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    items: list[ExecutionItemRead] = Field(default_factory=list)


class ExecutionListData(BaseModel):
    items: list[ExecutionRead]
    total: int
    page: int
    page_size: int
