from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.observability import get_logger, log_event
from backend.app.core.timezone import to_beijing_isoformat
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

logger = get_logger("auth")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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
            log_event(logger, "auth.bootstrap_admin.exists", username=existing.username, user_id=existing.id)
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
        log_event(logger, "auth.bootstrap_admin.created", username=user.username, user_id=user.id)

    def authenticate(self, username: str, password: str) -> User:
        user = self._users.get_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            log_event(logger, "auth.login.failed", level=logging.WARNING, username=username, reason="invalid_credentials")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")
        if not user.is_active:
            log_event(
                logger,
                "auth.login.blocked",
                level=logging.WARNING,
                username=username,
                user_id=user.id,
                reason="user_disabled",
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is disabled.")
        log_event(logger, "auth.login.succeeded", username=user.username, user_id=user.id, role=user.role)
        return user

    def build_session(self, user: User) -> AuthSessionRead:
        issued_at = _utc_now()
        token = generate_access_token()
        expires_at = issued_at + timedelta(hours=settings.auth_token_ttl_hours)
        self._enforce_active_token_limit(user.id, issued_at)
        self._users.save_token(
            AccessToken(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=expires_at,
            )
        )
        self._session.flush()
        log_event(
            logger,
            "auth.session.issued",
            user_id=user.id,
            username=user.username,
            expires_at=expires_at,
            max_active_tokens=settings.auth_max_active_tokens_per_user,
        )
        return AuthSessionRead(
            access_token=token,
            issued_at=to_beijing_isoformat(issued_at),
            expires_at=to_beijing_isoformat(expires_at),
            expires_in_seconds=settings.auth_token_ttl_hours * 3600,
            user=UserRead.model_validate(user),
        )

    def resolve_user(self, token: str | None) -> User | None:
        if not token:
            return None
        access_token = self._users.get_token(hash_token(token))
        if access_token is None or access_token.revoked_at is not None:
            return None
        if _as_utc(access_token.expires_at) < _utc_now():
            return None
        if not access_token.user.is_active:
            return None
        return access_token.user

    def revoke_access_token(self, token: str) -> None:
        self._users.revoke_token(hash_token(token))
        log_event(logger, "auth.session.revoked")

    def list_users(self) -> list[User]:
        return self._users.list_users()

    def list_users_page(self, *, page: int = 1, page_size: int = 20) -> tuple[list[User], int]:
        return self._users.list_users_page(page=page, page_size=page_size)

    def create_user(self, username: str, display_name: str, password: str, role: UserRole) -> User:
        if self._users.get_by_username(username) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists.")
        self._validate_password(password)
        user = User(
            username=username,
            display_name=display_name,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        created_user = self._users.create(user)
        log_event(logger, "auth.user.created", user_id=created_user.id, username=created_user.username, role=created_user.role)
        return created_user

    def set_user_active_state(self, target_user_id: int, *, is_active: bool, actor: User) -> User:
        target_user = self._users.get_by_id(target_user_id)
        if target_user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        if target_user.id == actor.id and not is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot disable your own account.")
        if target_user.role == UserRole.admin and not is_active:
            active_admins = self._users.count_active_admins(exclude_user_id=target_user.id)
            if active_admins == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The last active admin cannot be disabled.",
                )
        if target_user.is_active == is_active:
            return target_user
        target_user.is_active = is_active
        if not is_active:
            self._users.revoke_all_tokens_for_user(target_user.id, revoked_at=_utc_now())
        self._session.flush()
        log_event(
            logger,
            "auth.user.status_changed",
            actor_user_id=actor.id,
            actor_username=actor.username,
            target_user_id=target_user.id,
            target_username=target_user.username,
            is_active=target_user.is_active,
        )
        return target_user

    def _validate_bootstrap_admin_settings(self) -> None:
        username = settings.bootstrap_admin_username.strip()
        password = settings.bootstrap_admin_password
        if not username:
            raise RuntimeError("Bootstrap admin is enabled, but EAZYTEST_BOOTSTRAP_ADMIN_USERNAME is missing.")
        if not password:
            raise RuntimeError("Bootstrap admin is enabled, but EAZYTEST_BOOTSTRAP_ADMIN_PASSWORD is missing.")
        if is_default_weak_password(password):
            raise RuntimeError("Bootstrap admin cannot use a known weak password.")
        try:
            validate_password_strength(password, min_length=settings.user_password_min_length)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc

    def _validate_password(self, password: str) -> None:
        if is_default_weak_password(password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Weak passwords are not allowed.")
        try:
            validate_password_strength(password, min_length=settings.user_password_min_length)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    def _enforce_active_token_limit(self, user_id: int, now: datetime) -> None:
        active_tokens = self._users.list_active_tokens(user_id, now=now)
        keep_count = max(settings.auth_max_active_tokens_per_user - 1, 0)
        if len(active_tokens) <= keep_count:
            return
        self._users.revoke_tokens(active_tokens[keep_count:], revoked_at=now)
