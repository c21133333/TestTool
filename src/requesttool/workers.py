from PySide6.QtCore import QObject, Signal

from assertions import AssertionEngine
from requesttool import http_client
from requesttool import processor_engine


class ApiRequestWorker(QObject):
    finished = Signal(dict)
    error = Signal(dict)
    progress = Signal(str)

    def __init__(self, request_data: dict, assertion_data: list, pre_processors: list, post_processors: list) -> None:
        super().__init__()
        self.request_data = request_data
        self.assertion_data = assertion_data
        self.pre_processors = pre_processors
        self.post_processors = post_processors
        self.assertion_engine = AssertionEngine()

    def run(self) -> None:
        try:
            result, assertion_results, _context = processor_engine.execute_request(
                self.request_data,
                self.assertion_data,
                self.pre_processors,
                self.post_processors,
                http_client,
                self.assertion_engine,
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
