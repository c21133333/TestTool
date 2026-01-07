from __future__ import annotations

from typing import Any


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
                    "error_type": "BatchExecutorError",
                    "error_message": str(exc),
                },
                "assertion_results": [],
                "result": "FAIL",
                "logs": [],
                "db_assertions": [],
                "attachments": [],
            }
