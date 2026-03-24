from __future__ import annotations

from pydantic import BaseModel

from backend.app.schemas.user import UserRead


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthSessionRead(BaseModel):
    access_token: str
    token_type: str = "bearer"
    issued_at: str
    expires_at: str
    expires_in_seconds: int
    user: UserRead
