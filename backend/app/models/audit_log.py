from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin


class AuditLog(TimestampMixin, Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    details_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    user = relationship("User")

    @property
    def actor_username(self) -> str | None:
        return self.user.username if self.user is not None else None

    @property
    def actor_display_name(self) -> str | None:
        return self.user.display_name if self.user is not None else None

    @property
    def actor_role(self) -> str | None:
        return self.user.role.value if self.user is not None else None
