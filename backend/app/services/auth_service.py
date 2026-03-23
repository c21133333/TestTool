from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.security import (
    generate_access_token,
    hash_password,
    hash_token,
    is_default_weak_password,
    validate_password_strength,
    verify_password,
)
from backend.app.models.access_token import AccessToken
from backend.app.models.user import User, UserRole
from backend.app.repositories.user_repository import UserRepository
from backend.app.schemas.auth import AuthSessionRead
from backend.app.schemas.user import UserRead


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AuthService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._users = UserRepository(session)

    def ensure_bootstrap_admin(self) -> None:
        if not settings.bootstrap_admin_enabled:
            return
        self._validate_bootstrap_admin_settings()
        existing = self._users.get_by_username(settings.bootstrap_admin_username)
        if existing is not None:
            return
        user = User(
            username=settings.bootstrap_admin_username,
            display_name="System Admin",
            password_hash=hash_password(settings.bootstrap_admin_password),
            role=UserRole.admin,
            is_active=True,
        )
        self._users.create(user)
        self._session.commit()

    def authenticate(self, username: str, password: str) -> User:
        user = self._users.get_by_username(username)
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误。")
        return user

    def build_session(self, user: User) -> AuthSessionRead:
        token = generate_access_token()
        expires_at = _utc_now() + timedelta(hours=settings.auth_token_ttl_hours)
        self._users.save_token(
            AccessToken(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=expires_at,
            )
        )
        self._session.flush()
        return AuthSessionRead(
            access_token=token,
            expires_at=expires_at.isoformat(),
            user=UserRead.model_validate(user),
        )

    def resolve_user(self, token: str | None) -> User | None:
        if not token:
            return None
        access_token = self._users.get_token(hash_token(token))
        if access_token is None or access_token.revoked_at is not None:
            return None
        if access_token.expires_at < _utc_now():
            return None
        return access_token.user

    def revoke_access_token(self, token: str) -> None:
        self._users.revoke_token(hash_token(token))

    def list_users(self) -> list[User]:
        return self._users.list_users()

    def create_user(self, username: str, display_name: str, password: str, role: UserRole) -> User:
        if self._users.get_by_username(username) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在。")
        self._validate_password(password)
        user = User(
            username=username,
            display_name=display_name,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        return self._users.create(user)

    def _validate_bootstrap_admin_settings(self) -> None:
        username = settings.bootstrap_admin_username.strip()
        password = settings.bootstrap_admin_password
        if not username:
            raise RuntimeError("已启用 bootstrap admin，但未配置 EAZYTEST_BOOTSTRAP_ADMIN_USERNAME。")
        if not password:
            raise RuntimeError("已启用 bootstrap admin，但未配置 EAZYTEST_BOOTSTRAP_ADMIN_PASSWORD。")
        if is_default_weak_password(password):
            raise RuntimeError("bootstrap admin 禁止使用默认弱口令，请改用高强度密码。")
        try:
            validate_password_strength(password, min_length=settings.user_password_min_length)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc

    def _validate_password(self, password: str) -> None:
        try:
            validate_password_strength(password, min_length=settings.user_password_min_length)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
