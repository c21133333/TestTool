from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class AiArtifact(TimestampMixin, Base):
    __tablename__ = "ai_artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    artifact_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    capability: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_id: Mapped[int] = mapped_column(nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    suite_id: Mapped[int | None] = mapped_column(ForeignKey("suites.id", ondelete="SET NULL"), nullable=True, index=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("api_cases.id", ondelete="SET NULL"), nullable=True, index=True)
    execution_id: Mapped[int | None] = mapped_column(ForeignKey("executions.id", ondelete="SET NULL"), nullable=True, index=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id", ondelete="SET NULL"), nullable=True, index=True)
    input_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    call_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="deterministic")
    latency_ms: Mapped[int | None] = mapped_column(nullable=True)
    failure_category: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    trace_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    @property
    def call_trace(self) -> dict:
        provider_payload = None
        if self.provider or self.model:
            provider_payload = {
                "provider": self.provider,
                "model": self.model,
                "base_url": "",
                "timeout_seconds": None,
            }
        return {
            "call_mode": self.call_mode,
            "provider": provider_payload,
            "latency_ms": self.latency_ms,
            "failure_category": self.failure_category,
            "trace_json": dict(self.trace_json or {}),
        }
