from PySide6.QtCore import QObject, Signal

from assertions import AssertionEngine
from requesttool import http_client


class ApiRequestWorker(QObject):
    finished = Signal(dict)
    error = Signal(dict)
    progress = Signal(str)

    def __init__(self, request_data: dict, assertion_data: list) -> None:
        super().__init__()
        self.request_data = request_data
        self.assertion_data = assertion_data
        self.assertion_engine = AssertionEngine()

    def run(self) -> None:
        try:
            result = http_client.send_request(self.request_data)
            assertion_results = []
            if result.get("success") is True:
                assertion_results = self.assertion_engine.run_assertions(
                    result,
                    self.assertion_data,
                )
            payload = {
                "response": result,
                "assertion_results": assertion_results,
            }
            self.finished.emit(payload)
        except Exception as exc:
            self.error.emit(
                {
                    "error_type": "WorkerError",
                    "error_message": str(exc),
                }
            )
