from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.access_token import AccessToken
from backend.app.models.user import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_username(self, username: str) -> User | None:
        return self._session.scalar(select(User).where(User.username == username))

    def get_by_id(self, user_id: int) -> User | None:
        return self._session.get(User, user_id)

    def list_users(self) -> list[User]:
        return list(self._session.scalars(select(User).order_by(User.username)).all())

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

    def revoke_token(self, token_hash: str) -> None:
        token = self.get_token(token_hash)
        if token is None or token.revoked_at is not None:
            return
        token.revoked_at = datetime.now(UTC).replace(tzinfo=None)
