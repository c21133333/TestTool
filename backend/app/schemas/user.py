from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from backend.app.models.user import UserRole


class UserCreate(BaseModel):
    username: str
    display_name: str
    password: str
    role: UserRole = UserRole.tester


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
