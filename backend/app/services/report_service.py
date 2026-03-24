from __future__ import annotations

import logging
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.observability import get_logger, log_event
from backend.app.models.execution import Execution
from backend.app.models.report import Report
from backend.app.repositories.report_repository import ReportRepository
from requesttool.shared.reporting import ReportGenerator

logger = get_logger("report")


class ReportService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._reports = ReportRepository(session)

    def list_reports(self) -> list[Report]:
        return self._reports.list_reports()

    def list_reports_page(self, *, page: int = 1, page_size: int = 20) -> tuple[list[Report], int]:
        return self._reports.list_reports_page(page=page, page_size=page_size)

    def get_report(self, report_id: int) -> Report:
        report = self._reports.get(report_id)
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
        return report

    def build_execution_report(self, execution: Execution) -> list[Report]:
        log_event(
            logger,
            "report.build.started",
            execution_id=execution.id,
            target_name=execution.target_name,
            item_count=len(execution.items),
        )
        items: list[dict] = []
        for item in sorted(execution.items, key=lambda entry: entry.order_index):
            assertions = []
            for assertion in item.assertion_results_json:
                assertions.append(
                    {
                        "name": assertion.get("type"),
                        "passed": assertion.get("result") == "PASS",
                        "actual": assertion.get("actual"),
                        "expected": assertion.get("expected"),
                        "message": assertion.get("message") or "",
                    }
                )
            items.append(
                {
                    "case_id": item.case_id,
                    "name": item.case_name,
                    "request": item.request_json,
                    "response": item.response_json,
                    "assertions": assertions,
                    "elapsed_ms": item.elapsed_ms,
                    "result": "OK" if item.status == "PASS" else "NG",
                    "failure_reason": item.failure_message,
                }
            )

        run_data = {
            "suite_name": execution.target_name,
            "base_url": execution.environment.base_url if execution.environment is not None else "",
            "execute_time": execution.finished_at.isoformat() if execution.finished_at else execution.created_at.isoformat(),
            "summary": execution.summary_json,
            "items": items,
        }
        try:
            settings.resolved_report_dir.mkdir(parents=True, exist_ok=True)
            generator = ReportGenerator(str(settings.resolved_report_template_path))
            paths = generator.generate(run_data, str(settings.resolved_report_dir))
            json_report = self._reports.create(
                Report(
                    execution_id=execution.id,
                    report_type="json",
                    file_path=str(Path(paths["json"]).resolve()),
                    metadata_json={"summary": execution.summary_json},
                )
            )
            html_report = self._reports.create(
                Report(
                    execution_id=execution.id,
                    report_type="html",
                    file_path=str(Path(paths["html"]).resolve()),
                    metadata_json={"summary": execution.summary_json},
                )
            )
        except Exception as exc:  # noqa: BLE001
            log_event(
                logger,
                "report.build.failed",
                level=logging.ERROR,
                execution_id=execution.id,
                target_name=execution.target_name,
                message=str(exc),
            )
            raise
        log_event(
            logger,
            "report.build.completed",
            execution_id=execution.id,
            report_paths=[json_report.file_path, html_report.file_path],
        )
        return [json_report, html_report]
