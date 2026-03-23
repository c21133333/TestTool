from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.models.execution import Execution, ExecutionItem, ExecutionScope, ExecutionStatus
from backend.app.models.user import User
from backend.app.repositories.execution_repository import ExecutionRepository
from backend.app.services.report_service import ReportService
from backend.app.services.workspace_service import WorkspaceService
from backend.app.testing.runtime import execute_case_payload


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ExecutionService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._executions = ExecutionRepository(session)
        self._workspace = WorkspaceService(session)
        self._reports = ReportService(session)

    def list_executions(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: ExecutionStatus | None = None,
        scope: ExecutionScope | None = None,
        search: str | None = None,
        failed_only: bool = False,
    ) -> tuple[list[Execution], int]:
        return self._executions.list_executions(
            page=page,
            page_size=page_size,
            status=status,
            scope=scope,
            search=search,
            failed_only=failed_only,
        )

    def get_execution(self, execution_id: int) -> Execution:
        execution = self._executions.get_execution(execution_id)
        if execution is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found.")
        return execution

    def run_case_now(self, case_id: int, environment_id: int | None, actor: User | None) -> Execution:
        case = self._workspace.get_case(case_id)
        environment = self._workspace.get_environment(environment_id) if environment_id is not None else None
        project_id = case.suite.project_id
        execution = Execution(
            project_id=project_id,
            suite_id=case.suite_id,
            environment_id=environment.id if environment is not None else None,
            triggered_by_user_id=actor.id if actor is not None else None,
            scope=ExecutionScope.case,
            status=ExecutionStatus.running,
            target_name=case.name,
            started_at=_utc_now(),
        )
        self._executions.create_execution(execution)

        payload = self._build_case_payload(case, environment)
        result = execute_case_payload(payload)
        self._append_item(execution, case.id, 1, result)
        self._finalize_execution(execution, [result])
        self._session.commit()
        self._reports.build_execution_report(execution)
        self._session.commit()
        return self.get_execution(execution.id)

    def queue_suite_execution(
        self,
        suite_id: int,
        environment_id: int | None,
        actor: User | None,
    ) -> Execution:
        suite = self._workspace.get_suite(suite_id)
        environment = self._workspace.get_environment(environment_id) if environment_id is not None else None
        execution = Execution(
            project_id=suite.project_id,
            suite_id=suite.id,
            environment_id=environment.id if environment is not None else None,
            triggered_by_user_id=actor.id if actor is not None else None,
            scope=ExecutionScope.suite,
            status=ExecutionStatus.pending,
            target_name=suite.name,
        )
        self._executions.create_execution(execution)
        self._session.commit()
        return self.get_execution(execution.id)

    def cancel_execution(self, execution_id: int) -> Execution:
        execution = self.get_execution(execution_id)
        if execution.scope != ExecutionScope.suite:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only suite executions can be canceled.")
        if execution.status in {ExecutionStatus.success, ExecutionStatus.failed}:
            return execution
        if execution.status == ExecutionStatus.pending:
            self._mark_execution_canceled(execution)
            self._session.commit()
            return self.get_execution(execution.id)
        control = dict(execution.summary_json or {})
        control["_control"] = {
            **(control.get("_control") or {}),
            "cancel_requested": True,
        }
        execution.summary_json = control
        self._executions.save_execution(execution)
        self._session.commit()
        return self.get_execution(execution.id)

    def retry_execution(self, execution_id: int, actor: User | None) -> Execution:
        execution = self.get_execution(execution_id)
        if execution.scope == ExecutionScope.case:
            if not execution.items or execution.items[0].case_id is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Original case reference is missing.")
            return self.run_case_now(execution.items[0].case_id, execution.environment_id, actor)
        if execution.suite_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Original suite reference is missing.")
        return self.queue_suite_execution(execution.suite_id, execution.environment_id, actor)

    def process_next_pending_execution(self) -> Execution | None:
        execution = self._executions.get_next_pending_execution()
        if execution is None:
            return None
        self.process_execution(execution.id)
        return self.get_execution(execution.id)

    def process_execution(self, execution_id: int) -> Execution:
        execution = self.get_execution(execution_id)
        if execution.scope != ExecutionScope.suite:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only suite executions can be processed.")
        if self._is_cancel_requested(execution):
            self._mark_execution_canceled(execution)
            self._session.commit()
            return self.get_execution(execution.id)
        suite = self._workspace.get_suite(execution.suite_id)
        environment = (
            self._workspace.get_environment(execution.environment_id)
            if execution.environment_id is not None
            else None
        )
        execution.status = ExecutionStatus.running
        execution.started_at = _utc_now()
        execution.error_message = ""
        self._session.commit()
        results: list[dict] = []
        try:
            for index, case in enumerate(suite.cases, start=1):
                if self._is_cancel_requested(execution):
                    self._mark_execution_canceled(execution, results)
                    self._session.commit()
                    return self.get_execution(execution.id)
                result = execute_case_payload(self._build_case_payload(case, environment))
                self._append_item(execution, case.id, index, result)
                results.append(result)
                self._session.commit()
            self._finalize_execution(execution, results)
            self._session.commit()
            self._reports.build_execution_report(execution)
            self._session.commit()
        except Exception as exc:
            execution.status = ExecutionStatus.failed
            execution.error_message = str(exc)
            execution.finished_at = _utc_now()
            self._session.commit()
        return self.get_execution(execution.id)

    def _build_case_payload(self, case, environment) -> dict:
        request_payload = {
            "method": case.method,
            "url": case.url,
            "headers": case.headers_json or {},
            "body": case.body_json,
        }
        if environment is not None:
            request_payload["base_url"] = environment.base_url
            request_payload["variables"] = environment.variables_json or {}
            merged_headers = dict(environment.headers_json or {})
            merged_headers.update(case.headers_json or {})
            request_payload["headers"] = merged_headers
        return {
            "case_id": str(case.id),
            "name": case.name,
            "request": request_payload,
            "assertions": case.assertions_json or [],
            "preProcessors": case.pre_processors_json or [],
            "postProcessors": case.post_processors_json or [],
        }

    def _append_item(self, execution: Execution, case_id: int | None, order_index: int, result: dict) -> None:
        response = result.get("response") or {}
        assertion_results = result.get("assertion_results") or []
        status_value = result.get("result") or "FAIL"
        failure_message = ""
        if status_value != "PASS":
            first_failure = next((item for item in assertion_results if item.get("result") != "PASS"), None)
            failure_message = response.get("error_message") or (first_failure or {}).get("message") or "Execution failed."
        self._executions.add_item(
            ExecutionItem(
                execution_id=execution.id,
                case_id=case_id,
                order_index=order_index,
                case_name=result.get("name") or execution.target_name,
                status=status_value,
                elapsed_ms=response.get("elapsed_ms"),
                request_json=result.get("request") or {},
                response_json=response,
                assertion_results_json=assertion_results,
                failure_message=failure_message,
            )
        )

    def _finalize_execution(self, execution: Execution, results: list[dict]) -> None:
        total = len(results)
        passed = sum(1 for result in results if result.get("result") == "PASS")
        failed = total - passed
        execution.summary_json = {
            "total": total,
            "ok": passed,
            "ng": failed,
            "pass_rate": round((passed / total) * 100, 2) if total else 0.0,
            "duration_ms": sum((result.get("response") or {}).get("elapsed_ms") or 0 for result in results),
        }
        execution.status = ExecutionStatus.success if failed == 0 else ExecutionStatus.failed
        execution.finished_at = _utc_now()

    def _is_cancel_requested(self, execution: Execution) -> bool:
        summary = execution.summary_json or {}
        control = summary.get("_control") if isinstance(summary, dict) else None
        return isinstance(control, dict) and bool(control.get("cancel_requested"))

    def _mark_execution_canceled(self, execution: Execution, results: list[dict] | None = None) -> None:
        safe_results = results or []
        total = len(safe_results)
        passed = sum(1 for result in safe_results if result.get("result") == "PASS")
        failed = total - passed
        execution.summary_json = {
            "total": total,
            "ok": passed,
            "ng": failed,
            "pass_rate": round((passed / total) * 100, 2) if total else 0.0,
            "duration_ms": sum((result.get("response") or {}).get("elapsed_ms") or 0 for result in safe_results),
            "_control": {
                "cancel_requested": False,
                "canceled": True,
            },
        }
        execution.status = ExecutionStatus.failed
        execution.error_message = "Canceled by user."
        execution.finished_at = _utc_now()
