from __future__ import annotations

from typing import Any

from requesttool import processor_engine


class BatchExecutor:
    def __init__(self, http_client, assertion_engine) -> None:
        self.http_client = http_client
        self.assertion_engine = assertion_engine

    def run_cases(self, cases: list) -> list:
        results: list[dict[str, Any]] = []
        for case in cases:
            results.append(self._run_single_case(case))
        return results

    def _run_single_case(self, case: dict) -> dict[str, Any]:
        try:
            return processor_engine.execute_case(case, self.http_client, self.assertion_engine)
        except Exception as exc:
            return {
                "case_id": case.get("case_id"),
                "name": case.get("name"),
                "request": case.get("request", {}),
                "assertions": case.get("assertions", []),
                "response": {
                    "success": False,
                    "error_type": "BatchExecutorError",
                    "error_message": str(exc),
                },
                "assertion_results": [],
                "result": "FAIL",
                "logs": [],
                "db_assertions": [],
                "attachments": [],
            }
