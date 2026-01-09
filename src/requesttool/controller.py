from datetime import datetime

from PySide6.QtCore import QObject, QThread, Slot

from assertions import AssertionEngine
from requesttool import http_client
from requesttool.batch_executor import BatchExecutor
from requesttool.batch_thread_executor import BatchThreadExecutor
from requesttool.result_exporter import ResultExporter
from requesttool.result_summary import build_summary
from requesttool.workers import ApiRequestWorker


class ApiTestController(QObject):
    def __init__(self, request_panel, response_panel, assertion_panel=None) -> None:
        super().__init__()
        self.request_panel = request_panel
        self.response_panel = response_panel
        self.assertion_panel = assertion_panel
        self.assertion_engine = AssertionEngine()
        self.last_assertion_results: list[dict] = []
        self.suite: dict | None = None
        self._thread: QThread | None = None
        self._worker: ApiRequestWorker | None = None
        self._request_done_cb = None
        self._request_error_cb = None
        self._batch_executor: BatchThreadExecutor | None = None
        self._request_running = False
        self._batch_running = False
        self._suite_name: str | None = None
        self._suite_output_dir: str | None = None
        self._suite_on_finished = None
        self._batch_canceled = False
        self._request_thread_active = False

    def send_request(self) -> None:
        try:
            print("Request started")
            self.response_panel.clear()
            updater = getattr(self.response_panel, "clear_assertion_results", None)
            if callable(updater):
                updater()
            params = self.request_panel.get_request_data()
            method = params.get("method")
            if isinstance(method, str):
                params["method"] = method.upper()
            if params.get("headers") is None:
                params["headers"] = {}
            if params.get("body") is None:
                params.pop("body", None)
            if params.get("timeout") is None:
                params["timeout"] = 20
            result = http_client.send_request(params)
            self.response_panel.update_response(result)
            if result.get("success") is True:
                assertions = self._get_assertions()
                self.last_assertion_results = self.assertion_engine.run_assertions(
                    result,
                    assertions,
                )
                updater = getattr(self.response_panel, "update_assertion_results", None)
                if callable(updater):
                    updater(self.last_assertion_results)
            print("Request finished")
        except Exception as exc:
            error_result = {
                "success": False,
                "error_type": "ControllerError",
                "error_message": str(exc),
            }
            self.response_panel.update_response(error_result)
            print("Request failed")

    def send_request_async(self, on_finished=None, on_error=None) -> None:
        try:
            if self._request_running:
                return
            self._request_running = True
            self.response_panel.clear()
            append_log = getattr(self.response_panel, "append_log", None)
            if callable(append_log):
                append_log("request_started")
            updater = getattr(self.response_panel, "clear_assertion_results", None)
            if callable(updater):
                updater()
            params = self.request_panel.get_request_data()
            method = params.get("method")
            if isinstance(method, str):
                params["method"] = method.upper()
            if params.get("headers") is None:
                params["headers"] = {}
            if params.get("body") is None:
                params.pop("body", None)
            if params.get("timeout") is None:
                params["timeout"] = 20

            assertions = self._get_assertions()
            if callable(append_log):
                append_log(f"assertions_enabled={len(assertions)}")
            thread = QThread(self)
            worker = ApiRequestWorker(params, assertions)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)

            worker.finished.connect(self._on_async_finished)
            worker.error.connect(self._on_async_error)
            worker.finished.connect(thread.quit)
            worker.error.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            worker.error.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(self._on_request_thread_finished)

            self._thread = thread
            self._worker = worker
            self._request_done_cb = on_finished
            self._request_error_cb = on_error
            self._request_thread_active = True
            thread.start()
        except Exception as exc:
            self._request_running = False
            error_result = {
                "success": False,
                "error_type": "ControllerError",
                "error_message": str(exc),
            }
            self.response_panel.update_response(error_result)
            if callable(on_error):
                on_error(error_result)

    @Slot(dict)
    def _on_async_finished(self, payload: dict) -> None:
        response_result = payload.get("response") or {}
        assertion_results = payload.get("assertion_results") or []
        self.response_panel.update_response(response_result)
        append_log = getattr(self.response_panel, "append_log", None)
        if callable(append_log):
            append_log("request_finished")
        updater = getattr(self.response_panel, "update_assertion_results", None)
        if callable(updater):
            updater(assertion_results)
        if callable(self._request_done_cb):
            self._request_done_cb(response_result)

    @Slot(dict)
    def _on_async_error(self, error_info: dict) -> None:
        error_result = {
            "success": False,
            "error_type": error_info.get("error_type", "WorkerError"),
            "error_message": error_info.get("error_message", ""),
        }
        self.response_panel.update_response(error_result)
        append_log = getattr(self.response_panel, "append_log", None)
        if callable(append_log):
            append_log(f"request_error={error_result.get('error_type')}")
        if callable(self._request_error_cb):
            self._request_error_cb(error_result)

    @Slot()
    def _on_request_thread_finished(self) -> None:
        self._request_running = False
        self._request_thread_active = False
        self._thread = None
        self._worker = None

    def _get_assertions(self) -> list:
        if self.assertion_panel is None:
            return []
        getter = getattr(self.assertion_panel, "get_assertions", None)
        if callable(getter):
            return getter()
        return []

    def run_suite(self) -> None:
        try:
            suite = self.suite or {"suite_name": "default_suite", "cases": []}
            suite_name = suite.get("suite_name") or "default_suite"
            cases = suite.get("cases") or []
            output_dir = suite.get("output_dir") or "results"

            executor = BatchExecutor(http_client, self.assertion_engine)
            case_results = executor.run_cases(cases)
            summary = build_summary(case_results)

            result = {
                "suite_name": suite_name,
                "execute_time": datetime.now().isoformat(),
                "summary": summary,
                "cases": case_results,
            }
            exporter = ResultExporter()
            path = exporter.export_json(result, output_dir)
            return result, path
        except Exception as exc:
            result = {
                "suite_name": "default_suite",
                "execute_time": datetime.now().isoformat(),
                "summary": {"total": 0, "pass": 0, "fail": 0},
                "cases": [],
                "error": str(exc),
            }
            return result, "-"

    def set_suite(self, suite: dict) -> None:
        self.suite = suite

    def run_suite_async(self, on_progress=None, on_finished=None, on_case_started=None, on_case_finished=None) -> None:
        try:
            if self._batch_running:
                return
            self._batch_running = True
            suite = self.suite or {"suite_name": "default_suite", "cases": []}
            suite_name = suite.get("suite_name") or "default_suite"
            cases = suite.get("cases") or []
            output_dir = suite.get("output_dir") or "results"

            executor = BatchThreadExecutor(http_client, self.assertion_engine)
            self._batch_executor = executor
            self._batch_canceled = False
            self._suite_name = suite_name
            self._suite_output_dir = output_dir
            self._suite_on_finished = on_finished

            if callable(on_progress):
                executor.progress.connect(on_progress)
            if callable(on_case_started):
                executor.case_started.connect(on_case_started)
            if callable(on_case_finished):
                executor.case_finished.connect(on_case_finished)
            executor.finished.connect(self._on_suite_finished)
            executor.start(cases)
        except Exception as exc:
            self._batch_running = False
            if callable(on_finished):
                result = {
                    "suite_name": "default_suite",
                    "execute_time": datetime.now().isoformat(),
                    "summary": {"total": 0, "pass": 0, "fail": 0},
                    "cases": [],
                    "error": str(exc),
                }
                on_finished(result, "-")

    @Slot(object)
    def _on_suite_finished(self, case_results: list) -> None:
        summary = build_summary(case_results)
        result = {
            "suite_name": self._suite_name or "default_suite",
            "execute_time": datetime.now().isoformat(),
            "summary": summary,
            "cases": case_results,
            "canceled": self._batch_canceled,
        }
        exporter = ResultExporter()
        output_dir = self._suite_output_dir or "results"
        path = exporter.export_json(result, output_dir)
        if callable(self._suite_on_finished):
            self._suite_on_finished(result, path)
        self._batch_executor = None
        self._batch_canceled = False
        self._batch_running = False
        self._suite_name = None
        self._suite_output_dir = None
        self._suite_on_finished = None

    def cancel_suite(self) -> None:
        if self._batch_executor is None:
            return
        self._batch_canceled = True
        self._batch_executor.cancel()
