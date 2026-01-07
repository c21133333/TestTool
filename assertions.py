from __future__ import annotations

from typing import Any

from jsonpath_ng import parse


class AssertionEngine:
    def run_assertions(self, response_result: dict, assertions: list) -> list:
        results: list[dict[str, Any]] = []
        for assertion in assertions:
            result = self._run_single(response_result, assertion)
            results.append(result)
        return results

    def _run_single(self, response_result: dict, assertion: dict) -> dict[str, Any]:
        try:
            assertion_type = assertion.get("type")
            if assertion_type == "status_code":
                expected = assertion.get("expected")
                actual = response_result.get("status_code")
                passed = actual == expected
                return self._build_result(
                    assertion_type,
                    passed,
                    expected,
                    actual,
                    "" if passed else f"status_code {actual} != {expected}",
                )
            if assertion_type == "json_path":
                return self._run_json_path(response_result, assertion)
            return self._build_result(
                assertion_type,
                False,
                assertion.get("expected"),
                None,
                "不支持的断言类型",
            )
        except Exception as exc:
            return self._build_result(
                assertion.get("type"),
                False,
                assertion.get("expected"),
                None,
                f"exception: {exc}",
            )

    def _run_json_path(self, response_result: dict, assertion: dict) -> dict[str, Any]:
        operator = assertion.get("operator")
        path = assertion.get("path")
        expected = assertion.get("expected")

        try:
            json_data = response_result.get("response_json")
            if json_data is None:
                return self._build_result(
                    "json_path",
                    False,
                    expected,
                    None,
                    "response_json is None",
                )
            matches = [match.value for match in parse(path).find(json_data)]
        except Exception as exc:
            return self._build_result(
                "json_path",
                False,
                expected,
                None,
                f"json_path error: {exc}",
            )

        if not matches:
            return self._build_result(
                "json_path",
                False,
                expected,
                None,
                f"{path} not found",
            )

        actual = matches[0] if len(matches) == 1 else matches

        if operator == "equals":
            passed = actual == expected
            message = "" if passed else f"{path} {actual} != {expected}"
            return self._build_result("json_path", passed, expected, actual, message)

        if operator == "not_null":
            passed = any(self._is_not_empty(value) for value in matches)
            message = "" if passed else f"{path} is null or empty"
            expected_value = expected if expected is not None else "not_null"
            return self._build_result("json_path", passed, expected_value, actual, message)

        return self._build_result(
            "json_path",
            False,
            expected,
            actual,
            f"unsupported operator: {operator}",
        )

    def _build_result(
        self,
        assertion_type: str,
        passed: bool,
        expected: Any,
        actual: Any,
        message: str,
    ) -> dict[str, Any]:
        return {
            "type": assertion_type,
            "result": "PASS" if passed else "FAIL",
            "expected": expected,
            "actual": actual,
            "message": message,
        }

    def _is_not_empty(self, value: Any) -> bool:
        return value not in (None, "", [])


if __name__ == "__main__":
    engine = AssertionEngine()
    response = {
        "status_code": 200,
        "response_json": {"data": {"id": 1001, "name": "demo"}},
    }
    assertions = [
        {"type": "status_code", "expected": 200},
        {"type": "json_path", "path": "$.data.id", "operator": "equals", "expected": 1001},
        {"type": "json_path", "path": "$.data.name", "operator": "not_null"},
    ]
    print(engine.run_assertions(response, assertions))
