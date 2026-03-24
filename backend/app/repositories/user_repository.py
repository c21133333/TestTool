from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.access_token import AccessToken
from backend.app.models.user import User, UserRole


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_username(self, username: str) -> User | None:
        return self._session.scalar(select(User).where(User.username == username))

    def get_by_id(self, user_id: int) -> User | None:
        return self._session.get(User, user_id)

    def list_users(self) -> list[User]:
        return list(self._session.scalars(select(User).order_by(User.username)).all())

    def list_users_page(self, *, page: int, page_size: int) -> tuple[list[User], int]:
        stmt = select(User).order_by(User.username)
        count_stmt = select(func.count(User.id)).select_from(User)
        total = int(self._session.scalar(count_stmt) or 0)
        paged_stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        return list(self._session.scalars(paged_stmt).all()), total

    def create(self, user: User) -> User:
        self._session.add(user)
        self._session.flush()
        return user

    def save_token(self, token: AccessToken) -> AccessToken:
        self._session.add(token)
        self._session.flush()
        return token

    def get_token(self, token_hash: str) -> AccessToken | None:
        return self._session.scalar(select(AccessToken).where(AccessToken.token_hash == token_hash))

    def list_active_tokens(self, user_id: int, *, now: datetime) -> list[AccessToken]:
        statement = (
            select(AccessToken)
            .where(
                AccessToken.user_id == user_id,
                AccessToken.revoked_at.is_(None),
                AccessToken.expires_at >= now,
            )
            .order_by(AccessToken.created_at.desc(), AccessToken.id.desc())
        )
        return list(self._session.scalars(statement).all())

    def revoke_token(self, token_hash: str) -> None:
        token = self.get_token(token_hash)
        if token is None or token.revoked_at is not None:
            return
        token.revoked_at = datetime.now(UTC)

    def revoke_tokens(self, tokens: list[AccessToken], *, revoked_at: datetime) -> None:
        for token in tokens:
            if token.revoked_at is None:
                token.revoked_at = revoked_at

    def revoke_all_tokens_for_user(self, user_id: int, *, revoked_at: datetime) -> None:
        tokens = self._session.scalars(
            select(AccessToken).where(
                AccessToken.user_id == user_id,
                AccessToken.revoked_at.is_(None),
            )
        ).all()
        self.revoke_tokens(list(tokens), revoked_at=revoked_at)

    def count_active_admins(self, *, exclude_user_id: int | None = None) -> int:
        statement = select(func.count()).select_from(User).where(
            User.role == UserRole.admin,
            User.is_active.is_(True),
        )
        if exclude_user_id is not None:
            statement = statement.where(User.id != exclude_user_id)
        return int(self._session.scalar(statement) or 0)
