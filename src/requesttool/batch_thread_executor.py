from __future__ import annotations

from threading import Lock
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _CaseRunnable(QRunnable):
    def __init__(self, case: dict, runner, on_done) -> None:
        super().__init__()
        self.case = case
        self.runner = runner
        self.on_done = on_done

    def run(self) -> None:
        result = self.runner(self.case)
        self.on_done(result)


class BatchThreadExecutor(QObject):
    progress = Signal(int, int)
    finished = Signal(object)

    def __init__(self, http_client, assertion_engine, max_workers: int = 5) -> None:
        super().__init__()
        self.http_client = http_client
        self.assertion_engine = assertion_engine
        self.max_workers = max_workers
        self._lock = Lock()
        self._results: list[dict[str, Any]] = []
        self._total = 0
        self._completed = 0
        self._pending: list[dict[str, Any]] = []
        self._active = 0
        self._canceled = False

    def run_cases(self, cases: list) -> list:
        pool = QThreadPool()
        pool.setMaxThreadCount(self.max_workers)
        results: list[dict[str, Any]] = []
        lock = Lock()
        def on_done(result: dict[str, Any]) -> None:
            with lock:
                results.append(result)
        for case in cases:
            task = _CaseRunnable(case, self._run_single_case, on_done)
            pool.start(task)
        pool.waitForDone()
        return results

    def start(self, cases: list) -> None:
        self._results = []
        self._total = len(cases)
        self._completed = 0
        self._pending = list(cases)
        self._active = 0
        self._canceled = False
        if self._total == 0:
            self.finished.emit([])
            return
        pool = QThreadPool.globalInstance()
        pool.setMaxThreadCount(self.max_workers)
        self._start_next(pool)

    def cancel(self) -> None:
        with self._lock:
            self._canceled = True
            self._pending.clear()
            if self._active == 0:
                self.finished.emit(list(self._results))

    @property
    def canceled(self) -> bool:
        return self._canceled

    def _on_case_done(self, result: dict[str, Any]) -> None:
        with self._lock:
            self._results.append(result)
            self._completed += 1
            self._active = max(0, self._active - 1)
            self.progress.emit(self._completed, self._total)
            if not self._canceled:
                pool = QThreadPool.globalInstance()
                self._start_next(pool)
            if self._completed >= self._total or (self._canceled and self._active == 0):
                self.finished.emit(list(self._results))

    def _start_next(self, pool: QThreadPool) -> None:
        while self._active < self.max_workers and self._pending:
            case = self._pending.pop(0)
            task = _CaseRunnable(case, self._run_single_case, self._on_case_done)
            self._active += 1
            pool.start(task)

    def _run_single_case(self, case: dict) -> dict[str, Any]:
        try:
            request_data = case.get("request", {})
            assertions = case.get("assertions", [])
            response_result = self.http_client.send_request(request_data)
            assertion_results = self.assertion_engine.run_assertions(
                response_result,
                assertions,
            )
            if response_result.get("success") is False:
                result = "FAIL"
            else:
                passed = all(item.get("result") == "PASS" for item in assertion_results)
                result = "PASS" if passed else "FAIL"
            return {
                "case_id": case.get("case_id"),
                "name": case.get("name"),
                "request": request_data,
                "assertions": assertions,
                "response": response_result,
                "assertion_results": assertion_results,
                "result": result,
                "logs": [],
                "db_assertions": [],
                "attachments": [],
            }
        except Exception as exc:
            return {
                "case_id": case.get("case_id"),
                "name": case.get("name"),
                "request": case.get("request", {}),
                "assertions": case.get("assertions", []),
                "response": {
                    "success": False,
                    "error_type": "BatchThreadExecutorError",
                    "error_message": str(exc),
                },
                "assertion_results": [],
                "result": "FAIL",
                "logs": [],
                "db_assertions": [],
                "attachments": [],
            }
