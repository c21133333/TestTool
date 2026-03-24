from __future__ import annotations

from sqlalchemy import func, select
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

    def list_reports_page(self, *, page: int, page_size: int) -> tuple[list[Report], int]:
        stmt = select(Report).order_by(Report.created_at.desc())
        count_stmt = select(func.count(Report.id)).select_from(Report)
        total = int(self._session.scalar(count_stmt) or 0)
        paged_stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        return list(self._session.scalars(paged_stmt).all()), total
