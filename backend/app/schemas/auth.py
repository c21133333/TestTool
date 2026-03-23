from __future__ import annotations

from pydantic import BaseModel

from backend.app.schemas.user import UserRead


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthSessionRead(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str
    user: UserRead
