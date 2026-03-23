from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    action: str
    resource_type: str
    resource_id: str
    summary: str
    details_json: dict
    actor_username: str | None = None
    actor_display_name: str | None = None
    actor_role: str | None = None
    created_at: datetime


class AuditLogListData(BaseModel):
    items: list[AuditLogRead]
    total: int
    page: int
    page_size: int
