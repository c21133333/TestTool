from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.report import Report


class ReportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, report: Report) -> Report:
        self._session.add(report)
        self._session.flush()
        return report

    def get(self, report_id: int) -> Report | None:
        return self._session.get(Report, report_id)

    def list_reports(self) -> list[Report]:
        return list(self._session.scalars(select(Report).order_by(Report.created_at.desc())).all())
