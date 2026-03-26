from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    admin = "admin"
    tester = "tester"
    developer = "developer"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False, default=UserRole.tester)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    tokens = relationship("AccessToken", back_populates="user", cascade="all, delete-orphan")
    ai_chat_sessions = relationship("AiChatSession", back_populates="user", cascade="all, delete-orphan")
