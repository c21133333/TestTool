from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.observability import get_logger, log_event
from backend.app.core.timezone import to_beijing_isoformat
from backend.app.models.execution import Execution, ExecutionItem, ExecutionScope, ExecutionStatus
from backend.app.models.user import User
from backend.app.repositories.execution_repository import ExecutionRepository
from backend.app.schemas.execution import AiExecutionPreparationSelection
from backend.app.services.ai_execution_preparation_service import AiExecutionPreparationService
from backend.app.services.report_service import ReportService
from backend.app.services.workspace_service import WorkspaceService
from backend.app.testing.runtime import execute_case_payload


TRANSIENT_FAILURE_CATEGORIES = {"timeout", "request_error"}
logger = get_logger("execution")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ExecutionService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._executions = ExecutionRepository(session)
        self._workspace = WorkspaceService(session)
        self._preparation_service = AiExecutionPreparationService(session)
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

    def run_case_now(
        self,
        case_id: int,
        environment_id: int | None,
        actor: User | None,
        *,
        ai_preparation: AiExecutionPreparationSelection | None = None,
    ) -> Execution:
        case = self._workspace.get_case(case_id)
        environment = self._workspace.get_environment(environment_id) if environment_id is not None else None
        preparation = self._preparation_service.build_case_preparation(case_id=case_id, selection=ai_preparation)
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
        log_event(
            logger,
            "execution.case.started",
            execution_id=execution.id,
            case_id=case.id,
            case_name=case.name,
            environment_id=environment.id if environment is not None else None,
            triggered_by_user_id=actor.id if actor is not None else None,
        )

        results: list[dict[str, Any]] = []
        try:
            result = self._execute_case_with_retries(case, environment, preparation=preparation)
            self._append_item(execution, case.id, 1, result)
            results.append(result)
            self._finalize_execution(execution, results, ai_preparation_summary=preparation.summary)
            self._session.commit()
            self._build_reports_if_items(execution)
            log_event(
                logger,
                "execution.case.completed",
                execution_id=execution.id,
                status=execution.status,
                summary=execution.summary_json,
            )
        except Exception as exc:  # noqa: BLE001
            self._fail_execution(
                execution,
                results,
                failure_category="runtime_error",
                message=str(exc),
                ai_preparation_summary=preparation.summary,
            )
            self._session.commit()
            self._build_reports_if_items(execution)
            log_event(
                logger,
                "execution.case.failed",
                level=logging.ERROR,
                execution_id=execution.id,
                error_message=str(exc),
                summary=execution.summary_json,
            )
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
            summary_json={},
        )
        self._executions.create_execution(execution)
        self._session.commit()
        log_event(
            logger,
            "execution.suite.queued",
            execution_id=execution.id,
            suite_id=suite.id,
            suite_name=suite.name,
            environment_id=environment.id if environment is not None else None,
            triggered_by_user_id=actor.id if actor is not None else None,
        )
        return self.get_execution(execution.id)

    def cancel_execution(self, execution_id: int) -> Execution:
        execution = self.get_execution(execution_id)
        if execution.scope != ExecutionScope.suite:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only suite executions can be canceled.")
        if execution.status in {ExecutionStatus.success, ExecutionStatus.failed}:
            return execution
        if execution.status == ExecutionStatus.pending:
            self._mark_execution_canceled(execution, stage="queued")
            self._session.commit()
            log_event(logger, "execution.cancel.completed", execution_id=execution.id, stage="queued", status=execution.status)
            return self.get_execution(execution.id)
        control = dict(execution.summary_json or {})
        control["_control"] = {
            **(control.get("_control") or {}),
            "cancel_requested": True,
            "cancel_requested_at": to_beijing_isoformat(_utc_now()),
        }
        execution.summary_json = control
        self._executions.save_execution(execution)
        self._session.commit()
        log_event(logger, "execution.cancel.requested", execution_id=execution.id, stage="running", status=execution.status)
        return self.get_execution(execution.id)

    def retry_execution(self, execution_id: int, actor: User | None) -> Execution:
        execution = self.get_execution(execution_id)
        if execution.status in {ExecutionStatus.pending, ExecutionStatus.running}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only completed executions can be retried.",
            )
        if execution.scope == ExecutionScope.case:
            if not execution.items or execution.items[0].case_id is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Original case reference is missing.")
            log_event(logger, "execution.retry.requested", execution_id=execution.id, scope=execution.scope)
            return self.run_case_now(execution.items[0].case_id, execution.environment_id, actor)
        if execution.suite_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Original suite reference is missing.")
        log_event(logger, "execution.retry.requested", execution_id=execution.id, scope=execution.scope)
        return self.queue_suite_execution(execution.suite_id, execution.environment_id, actor)

    def process_next_pending_execution(self) -> Execution | None:
        self.recover_stale_executions()
        execution = self._executions.get_next_pending_execution()
        if execution is None:
            return None
        self.process_execution(execution.id)
        return self.get_execution(execution.id)

    def recover_stale_executions(self) -> list[Execution]:
        cutoff = _utc_now() - timedelta(seconds=settings.execution_stale_timeout_seconds)
        stale_executions = self._executions.list_stale_running_executions(started_before=cutoff)
        if not stale_executions:
            return []
        recovered_at = _utc_now()
        for execution in stale_executions:
            control = self._merge_control(
                execution.summary_json,
                {
                    "cancel_requested": False,
                    "worker_stale": True,
                    "recovered_at": to_beijing_isoformat(recovered_at),
                },
            )
            execution.summary_json = self._build_summary_from_items(execution.items, control=control)
            execution.status = ExecutionStatus.failed
            execution.error_message = "Execution marked failed after worker stale timeout."
            execution.finished_at = recovered_at
            self._executions.save_execution(execution)
        self._session.commit()
        log_event(
            logger,
            "execution.stale.recovered",
            level=logging.WARNING,
            recovered_count=len(stale_executions),
            execution_ids=[execution.id for execution in stale_executions],
        )
        return [self.get_execution(execution.id) for execution in stale_executions]

    def process_execution(self, execution_id: int) -> Execution:
        execution = self.get_execution(execution_id)
        if execution.scope != ExecutionScope.suite:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only suite executions can be processed.")
        if execution.status == ExecutionStatus.failed and self._is_worker_stale(execution):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Stale executions must be retried as a new run.")
        if execution.status == ExecutionStatus.success:
            return execution
        if self._is_cancel_requested(execution):
            self._mark_execution_canceled(execution, stage="queued")
            self._session.commit()
            return self.get_execution(execution.id)

        if execution.suite_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Original suite reference is missing.")
        suite = self._workspace.get_suite(execution.suite_id)
        environment = (
            self._workspace.get_environment(execution.environment_id)
            if execution.environment_id is not None
            else None
        )
        execution.status = ExecutionStatus.running
        execution.started_at = _utc_now()
        execution.error_message = ""
        execution.summary_json = self._merge_control(execution.summary_json, {"cancel_requested": False})
        self._session.commit()
        log_event(logger, "execution.suite.started", execution_id=execution.id, suite_id=execution.suite_id, case_count=len(suite.cases))

        results: list[dict[str, Any]] = []
        shared_variables = self._build_initial_suite_variables(environment)
        try:
            for index, case in enumerate(suite.cases, start=1):
                if self._is_cancel_requested(execution):
                    self._mark_execution_canceled(execution, results, stage="running")
                    self._session.commit()
                    self._build_reports_if_items(execution)
                    log_event(
                        logger,
                        "execution.suite.canceled",
                        execution_id=execution.id,
                        status=execution.status,
                        summary=execution.summary_json,
                    )
                    return self.get_execution(execution.id)
                preparation = self._preparation_service.build_case_preparation(case_id=case.id, selection=None)
                result = self._execute_case_with_retries(
                    case,
                    environment,
                    preparation=preparation,
                    suite_variables=shared_variables,
                )
                self._append_item(execution, case.id, index, result)
                results.append(result)
                shared_variables = self._extract_runtime_variables(result, fallback=shared_variables)
                self._session.commit()
            self._finalize_execution(execution, results)
            self._session.commit()
            self._build_reports_if_items(execution)
            log_event(
                logger,
                "execution.suite.completed",
                execution_id=execution.id,
                status=execution.status,
                summary=execution.summary_json,
            )
        except Exception as exc:  # noqa: BLE001
            self._fail_execution(execution, results, failure_category="runtime_error", message=str(exc))
            self._session.commit()
            self._build_reports_if_items(execution)
            log_event(
                logger,
                "execution.suite.failed",
                level=logging.ERROR,
                execution_id=execution.id,
                error_message=str(exc),
                summary=execution.summary_json,
            )
        return self.get_execution(execution.id)

    def _execute_case_with_retries(
        self,
        case,
        environment,
        *,
        preparation,
        suite_variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        retry_history: list[dict[str, Any]] = []
        max_attempts = settings.execution_retry_limit + 1
        for attempt in range(1, max_attempts + 1):
            payload = self._build_case_payload(
                case,
                environment,
                preparation=preparation,
                suite_variables=suite_variables,
            )
            try:
                result = execute_case_payload(payload)
            except Exception as exc:  # noqa: BLE001
                result = self._build_runtime_exception_result(case, payload, exc)

            enriched = self._enrich_execution_result(result, attempt=attempt, retry_history=retry_history)
            if self._should_retry(enriched, attempt=attempt, max_attempts=max_attempts):
                response = enriched.get("response") or {}
                execution_meta = response.get("execution_meta") if isinstance(response.get("execution_meta"), dict) else {}
                log_event(
                    logger,
                    "execution.case.retry_scheduled",
                    level=logging.WARNING,
                    case_id=case.id,
                    case_name=case.name,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    failure_category=execution_meta.get("failure_category"),
                    failure_message=execution_meta.get("failure_message"),
                )
                retry_history.append(self._build_retry_history_entry(enriched))
                continue
            return enriched
        return enriched

    def _build_case_payload(
        self,
        case,
        environment,
        *,
        preparation,
        suite_variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = case.metadata_json if isinstance(case.metadata_json, dict) else {}
        configured_timeout = metadata.get("timeout_seconds") or metadata.get("timeout")
        try:
            timeout_seconds = max(1, int(configured_timeout))
        except Exception:
            timeout_seconds = settings.execution_request_timeout_seconds

        merged_variables = self._build_request_variables(
            environment.variables_json if environment is not None else None,
            suite_variables,
        )
        request_payload = {
            "method": case.method,
            "url": case.url,
            "headers": case.headers_json or {},
            "body": preparation.request_body,
            "timeout": timeout_seconds,
        }
        if merged_variables:
            request_payload["variables"] = merged_variables
        if environment is not None:
            request_payload["base_url"] = environment.base_url
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
            "aiPreparation": preparation.summary,
        }

    def _build_initial_suite_variables(self, environment) -> dict[str, Any]:
        return self._build_request_variables(environment.variables_json if environment is not None else None, None)

    def _build_request_variables(
        self,
        environment_variables: dict[str, Any] | None,
        suite_variables: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged_variables: dict[str, Any] = {}
        if isinstance(environment_variables, dict):
            merged_variables.update(environment_variables)
        if isinstance(suite_variables, dict):
            merged_variables.update(suite_variables)
        return merged_variables

    def _extract_runtime_variables(
        self,
        result: dict[str, Any],
        *,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        response = result.get("response") or {}
        runtime_variables = response.get("runtime_variables") if isinstance(response, dict) else None
        if not isinstance(runtime_variables, dict):
            return dict(fallback)
        return dict(runtime_variables)

    def _append_item(self, execution: Execution, case_id: int | None, order_index: int, result: dict[str, Any]) -> None:
        response = result.get("response") or {}
        assertion_results = result.get("assertion_results") or []
        execution_meta = response.get("execution_meta") if isinstance(response.get("execution_meta"), dict) else {}
        status_value = result.get("result") or "FAIL"
        failure_message = ""
        if status_value != "PASS":
            first_failure = next((item for item in assertion_results if item.get("result") != "PASS"), None)
            failure_message = (
                execution_meta.get("failure_message")
                or response.get("error_message")
                or (first_failure or {}).get("message")
                or "Execution failed."
            )
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

    def _finalize_execution(
        self,
        execution: Execution,
        results: list[dict[str, Any]],
        *,
        ai_preparation_summary: dict[str, Any] | None = None,
    ) -> None:
        execution.summary_json = self._build_summary_from_results(results, ai_preparation_summary=ai_preparation_summary)
        execution.status = ExecutionStatus.success if execution.summary_json.get("ng", 0) == 0 else ExecutionStatus.failed
        execution.error_message = execution.summary_json.get("first_failure", {}).get("message", "") if execution.status == ExecutionStatus.failed else ""
        execution.finished_at = _utc_now()

    def _fail_execution(
        self,
        execution: Execution,
        results: list[dict[str, Any]],
        *,
        failure_category: str,
        message: str,
        ai_preparation_summary: dict[str, Any] | None = None,
    ) -> None:
        control = self._merge_control(execution.summary_json, {})
        execution.summary_json = self._build_summary_from_results(
            results,
            control=control,
            extra_failure={"category": failure_category, "message": message},
            ai_preparation_summary=ai_preparation_summary,
        )
        execution.status = ExecutionStatus.failed
        execution.error_message = message
        execution.finished_at = _utc_now()

    def _is_cancel_requested(self, execution: Execution) -> bool:
        summary = execution.summary_json or {}
        control = summary.get("_control") if isinstance(summary, dict) else None
        return isinstance(control, dict) and bool(control.get("cancel_requested"))

    def _is_worker_stale(self, execution: Execution) -> bool:
        summary = execution.summary_json or {}
        control = summary.get("_control") if isinstance(summary, dict) else None
        return isinstance(control, dict) and bool(control.get("worker_stale"))

    def _mark_execution_canceled(
        self,
        execution: Execution,
        results: list[dict[str, Any]] | None = None,
        *,
        stage: str,
    ) -> None:
        control = self._merge_control(
            execution.summary_json,
            {
                "cancel_requested": False,
                "canceled": True,
                "cancel_stage": stage,
                "canceled_at": to_beijing_isoformat(_utc_now()),
            },
        )
        execution.summary_json = self._build_summary_from_results(
            results or [],
            control=control,
            extra_failure={"category": "canceled", "message": "Canceled by user."},
        )
        execution.status = ExecutionStatus.failed
        execution.error_message = "Canceled by user."
        execution.finished_at = _utc_now()

    def _should_retry(self, result: dict[str, Any], *, attempt: int, max_attempts: int) -> bool:
        if attempt >= max_attempts:
            return False
        response = result.get("response") or {}
        execution_meta = response.get("execution_meta") if isinstance(response.get("execution_meta"), dict) else {}
        failure_category = execution_meta.get("failure_category")
        return failure_category in TRANSIENT_FAILURE_CATEGORIES

    def _enrich_execution_result(
        self,
        result: dict[str, Any],
        *,
        attempt: int,
        retry_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        response = dict(result.get("response") or {})
        failure_category = self._classify_failure_category(result)
        failure_message = self._extract_failure_message(result, failure_category)
        response["execution_meta"] = {
            "failure_category": failure_category,
            "failure_message": failure_message,
            "attempt": attempt,
            "attempts": attempt,
            "retries": max(0, attempt - 1),
            "retried": attempt > 1,
            "retry_history": list(retry_history),
        }
        enriched = dict(result)
        enriched["response"] = response
        return enriched

    def _classify_failure_category(self, result: dict[str, Any]) -> str:
        response = result.get("response") or {}
        if response.get("success") is False:
            error_type = str(response.get("error_type") or "").strip()
            if error_type == "Timeout":
                return "timeout"
            if error_type in {"ConnectionError", "RequestException"}:
                return "request_error"
            if error_type == "PostProcessorAbort":
                return "processor_abort"
            if error_type in {"InvalidMethod", "InvalidURL"}:
                return "invalid_request"
            return "request_error"
        if result.get("result") == "PASS":
            return "success"
        return "assertion_failed"

    def _extract_failure_message(self, result: dict[str, Any], failure_category: str) -> str:
        if failure_category == "success":
            return ""
        response = result.get("response") or {}
        if response.get("error_message"):
            return str(response.get("error_message"))
        assertion_results = result.get("assertion_results") or []
        first_failure = next((item for item in assertion_results if item.get("result") != "PASS"), None)
        if first_failure and first_failure.get("message"):
            return str(first_failure.get("message"))
        return "Execution failed."

    def _build_runtime_exception_result(self, case, payload: dict[str, Any], exc: Exception) -> dict[str, Any]:
        return {
            "case_id": str(case.id),
            "name": case.name,
            "request": payload.get("request") or {},
            "assertions": payload.get("assertions") or [],
            "response": {
                "success": False,
                "error_type": "RuntimeError",
                "error_message": str(exc),
                "request_headers": (payload.get("request") or {}).get("headers") or {},
                "request_body": (payload.get("request") or {}).get("body"),
                "request_url": (payload.get("request") or {}).get("url"),
            },
            "assertion_results": [],
            "result": "FAIL",
            "logs": [],
            "db_assertions": [],
            "attachments": [],
        }

    def _build_retry_history_entry(self, result: dict[str, Any]) -> dict[str, Any]:
        response = result.get("response") or {}
        execution_meta = response.get("execution_meta") if isinstance(response.get("execution_meta"), dict) else {}
        return {
            "attempt": execution_meta.get("attempt"),
            "failure_category": execution_meta.get("failure_category"),
            "message": execution_meta.get("failure_message"),
            "error_type": response.get("error_type"),
        }

    def _build_summary_from_results(
        self,
        results: list[dict[str, Any]],
        *,
        control: dict[str, Any] | None = None,
        extra_failure: dict[str, Any] | None = None,
        ai_preparation_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        total = len(results)
        passed = sum(1 for result in results if result.get("result") == "PASS")
        failed = total - passed
        duration_ms = sum((result.get("response") or {}).get("elapsed_ms") or 0 for result in results)
        retry_total = sum(
            max(
                0,
                int(
                    ((result.get("response") or {}).get("execution_meta") or {}).get("retries") or 0
                ),
            )
            for result in results
        )
        failure_breakdown: dict[str, int] = {}
        first_failure: dict[str, Any] | None = None

        for result in results:
            response = result.get("response") or {}
            execution_meta = response.get("execution_meta") if isinstance(response.get("execution_meta"), dict) else {}
            category = execution_meta.get("failure_category")
            if category and category != "success":
                failure_breakdown[category] = failure_breakdown.get(category, 0) + 1
                if first_failure is None:
                    first_failure = {
                        "case_id": result.get("case_id"),
                        "case_name": result.get("name"),
                        "category": category,
                        "message": execution_meta.get("failure_message") or "",
                    }

        if extra_failure is not None:
            category = str(extra_failure.get("category") or "runtime_error")
            failure_breakdown[category] = failure_breakdown.get(category, 0) + 1
            failed += 1
            if first_failure is None:
                first_failure = {
                    "case_id": None,
                    "case_name": None,
                    "category": category,
                    "message": str(extra_failure.get("message") or ""),
                }

        summary = {
            "total": total,
            "ok": passed,
            "ng": failed,
            "pass_rate": round((passed / total) * 100, 2) if total else 0.0,
            "duration_ms": duration_ms,
            "failure_breakdown": failure_breakdown,
            "retry_stats": {
                "total_retries": retry_total,
                "retry_limit": settings.execution_retry_limit,
            },
        }
        if first_failure is not None:
            summary["first_failure"] = first_failure
        if ai_preparation_summary:
            summary["ai_preparation"] = dict(ai_preparation_summary)
        if control:
            summary["_control"] = control
        return summary

    def _build_summary_from_items(
        self,
        items: list[ExecutionItem],
        *,
        control: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        total = len(items)
        passed = sum(1 for item in items if item.status == "PASS")
        failed = total - passed
        duration_ms = sum(item.elapsed_ms or 0 for item in items)
        retry_total = 0
        failure_breakdown: dict[str, int] = {}
        first_failure: dict[str, Any] | None = None

        for item in items:
            execution_meta = (
                item.response_json.get("execution_meta")
                if isinstance(item.response_json, dict) and isinstance(item.response_json.get("execution_meta"), dict)
                else {}
            )
            retry_total += max(0, int(execution_meta.get("retries") or 0))
            category = execution_meta.get("failure_category")
            if item.status != "PASS":
                normalized_category = str(category or "assertion_failed")
                failure_breakdown[normalized_category] = failure_breakdown.get(normalized_category, 0) + 1
                if first_failure is None:
                    first_failure = {
                        "case_id": item.case_id,
                        "case_name": item.case_name,
                        "category": normalized_category,
                        "message": item.failure_message,
                    }

        summary = {
            "total": total,
            "ok": passed,
            "ng": failed,
            "pass_rate": round((passed / total) * 100, 2) if total else 0.0,
            "duration_ms": duration_ms,
            "failure_breakdown": failure_breakdown,
            "retry_stats": {
                "total_retries": retry_total,
                "retry_limit": settings.execution_retry_limit,
            },
        }
        if first_failure is not None:
            summary["first_failure"] = first_failure
        if control:
            summary["_control"] = control
        return summary

    def _merge_control(self, summary: dict[str, Any] | None, updates: dict[str, Any]) -> dict[str, Any]:
        current_summary = summary if isinstance(summary, dict) else {}
        current_control = current_summary.get("_control") if isinstance(current_summary.get("_control"), dict) else {}
        return {
            **current_control,
            **updates,
        }

    def _build_reports_if_items(self, execution: Execution) -> None:
        refreshed = self.get_execution(execution.id)
        if not refreshed.items:
            return
        self._reports.build_execution_report(refreshed)
        self._session.commit()
