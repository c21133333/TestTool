from __future__ import annotations

import json
import re
from typing import Any, Callable

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
                return self._run_status_code(response_result, assertion)
            if assertion_type == "response_body":
                return self._run_response_body(response_result, assertion)
            if assertion_type == "json_path":
                return self._run_json_path(response_result, assertion)
            if assertion_type == "header":
                return self._run_header(response_result, assertion)
            if assertion_type == "response_time":
                return self._run_response_time(response_result, assertion)
            return self._build_result(
                assertion_type,
                False,
                assertion.get("expected"),
                None,
                "不支持的断言类型",
                assertion,
            )
        except Exception as exc:
            return self._build_result(
                assertion.get("type"),
                False,
                assertion.get("expected"),
                None,
                f"exception: {exc}",
                assertion,
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
                    assertion,
                )
            matches = [match.value for match in parse(path).find(json_data)]
        except Exception as exc:
            return self._build_result(
                "json_path",
                False,
                expected,
                None,
                f"json_path error: {exc}",
                assertion,
            )

        if not matches:
            return self._build_result(
                "json_path",
                False,
                expected,
                None,
                f"{path} not found",
                assertion,
            )

        actual = matches[0] if len(matches) == 1 else matches

        if operator in {"exists", "not_exists"}:
            expected_value = operator
            has_value = bool(matches)
            passed = has_value if operator == "exists" else not has_value
            message = "" if passed else f"{path} {'not found' if operator == 'exists' else 'should not exist'}"
            actual_value = matches[0] if matches else None
            return self._build_result("json_path", passed, expected_value, actual_value, message, assertion)

        if operator in {"==", "equals"}:
            expected_value = self._normalize_expected(expected)
            passed = actual == expected_value
            message = (
                "" if passed else f"{path} {self._stringify_for_message(actual)} != {self._stringify_for_message(expected_value)}"
            )
            return self._build_result("json_path", passed, expected_value, actual, message, assertion)

        if operator == "not_null":
            expected_value = expected if expected is not None else "not_null"
            matches_value = matches[0] if len(matches) == 1 else matches
            passed = any(self._is_not_empty(value) for value in matches)
            message = "" if passed else f"{path} is null or empty"
            return self._build_result("json_path", passed, expected_value, matches_value, message, assertion)

        if operator in {">", ">=", "<", "<=", "!="}:
            expected_number = self._to_number(expected)
            if expected_number is None:
                return self._build_result(
                    "json_path",
                    False,
                    expected,
                    actual,
                    "expected number required for comparison",
                    assertion,
                )
            actual_number = None
            if isinstance(actual, (int, float)):
                actual_number = float(actual)
            else:
                actual_number = self._to_number(str(actual))
            if actual_number is None:
                return self._build_result(
                    "json_path",
                    False,
                    expected_number,
                    actual,
                    "actual value is not numeric",
                    assertion,
                )
            compare = self._compare_numeric(operator)
            if compare is None:
                return self._build_result(
                    "json_path",
                    False,
                    expected,
                    actual,
                    f"unsupported operator: {operator}",
                    assertion,
                )
            passed = compare(actual_number, expected_number)
            message = (
                "" if passed else f"{path} {self._stringify_for_message(actual_number)} {operator} {self._stringify_for_message(expected_number)} failed"
            )
            return self._build_result("json_path", passed, expected_number, actual, message, assertion)

        if operator in {"contains", "not_contains"}:
            needle = str(expected or "")
            haystack = "" if actual is None else str(actual)
            passed = needle in haystack if operator == "contains" else needle not in haystack
            message = "" if passed else f"{path} {operator} failed"
            return self._build_result("json_path", passed, expected, actual, message, assertion)

        return self._build_result(
            "json_path",
            False,
            expected,
            actual,
            f"unsupported operator: {operator}",
            assertion,
        )

    def _build_result(
        self,
        assertion_type: str,
        passed: bool,
        expected: Any,
        actual: Any,
        message: str,
        assertion: dict | None = None,
    ) -> dict[str, Any]:
        sanitized_message = self._sanitize_message(message)
        sanitized_expected = self._sanitize_value(expected)
        sanitized_actual = self._sanitize_value(actual)
        operator = None
        path = None
        header = None
        target = None
        if isinstance(assertion, dict):
            operator = assertion.get("operator")
            path = assertion.get("path")
            header = assertion.get("header")
            target = assertion.get("target")
        return {
            "type": assertion_type,
            "result": "PASS" if passed else "FAIL",
            "expected": sanitized_expected,
            "actual": sanitized_actual,
            "message": sanitized_message,
            "operator": operator,
            "path": path,
            "header": header,
            "target": target,
        }

    def _is_not_empty(self, value: Any) -> bool:
        return value not in (None, "", [])

    def _run_status_code(self, response_result: dict, assertion: dict) -> dict[str, Any]:
        operator = assertion.get("operator") or "=="
        expected_raw = assertion.get("expected")
        actual = response_result.get("status_code")
        if actual is None:
            return self._build_result("status_code", False, expected_raw, actual, "status_code missing", assertion)
        if operator == "between":
            range_values = self._parse_range(expected_raw)
            if range_values is None:
                return self._build_result("status_code", False, expected_raw, actual, "expected range required", assertion)
            lower, upper = range_values
            passed = lower <= actual <= upper
            message = (
                "" if passed else f"status_code {self._stringify_for_message(actual)} not in range {self._stringify_for_message(lower)}~{self._stringify_for_message(upper)}"
            )
            return self._build_result("status_code", passed, f"{lower}~{upper}", actual, message, assertion)
        expected = self._to_number(expected_raw)
        if expected is None:
            return self._build_result("status_code", False, expected_raw, actual, "expected number required", assertion)
        compare = self._compare_numeric(operator)
        if compare is None:
            return self._build_result("status_code", False, expected, actual, f"unsupported operator: {operator}", assertion)
        passed = compare(actual, expected)
        message = "" if passed else f"status_code {self._stringify_for_message(actual)} {operator} {self._stringify_for_message(expected)} failed"
        return self._build_result("status_code", passed, expected, actual, message, assertion)

    def _run_response_time(self, response_result: dict, assertion: dict) -> dict[str, Any]:
        operator = assertion.get("operator") or "<"
        expected_raw = assertion.get("expected")
        actual = response_result.get("elapsed_ms")
        if actual is None:
            return self._build_result("response_time", False, expected_raw, actual, "elapsed_ms missing", assertion)
        if operator == "between":
            range_values = self._parse_range(expected_raw)
            if range_values is None:
                return self._build_result("response_time", False, expected_raw, actual, "expected range required", assertion)
            lower, upper = range_values
            passed = lower <= actual <= upper
            message = (
                "" if passed else f"elapsed_ms {self._stringify_for_message(actual)} not in range {self._stringify_for_message(lower)}~{self._stringify_for_message(upper)}"
            )
            return self._build_result("response_time", passed, f"{lower}~{upper}", actual, message, assertion)
        expected = self._to_number(expected_raw)
        if expected is None:
            return self._build_result("response_time", False, expected_raw, actual, "expected number required", assertion)
        compare = self._compare_numeric(operator)
        if compare is None:
            return self._build_result("response_time", False, expected, actual, f"unsupported operator: {operator}", assertion)
        passed = compare(actual, expected)
        message = "" if passed else f"elapsed_ms {self._stringify_for_message(actual)} {operator} {self._stringify_for_message(expected)} failed"
        return self._build_result("response_time", passed, expected, actual, message, assertion)
    def _run_response_body(self, response_result: dict, assertion: dict) -> dict[str, Any]:
        operator = assertion.get("operator")
        expected = str(assertion.get("expected") or "")
        text = response_result.get("response_text") or ""
        if not text and response_result.get("response_json") is not None:
            text = json.dumps(response_result.get("response_json"), ensure_ascii=False)
        actual = text
        if operator == "contains":
            passed = expected in text
            message = "" if passed else "response body does not contain expected text"
            return self._build_result("response_body", passed, expected, actual, message, assertion)
        if operator == "not_contains":
            passed = expected not in text
            message = "" if passed else "response body contains expected text"
            return self._build_result("response_body", passed, expected, actual, message, assertion)
        if operator == "starts_with":
            passed = text.startswith(expected)
            message = "" if passed else "response body does not start with expected text"
            return self._build_result("response_body", passed, expected, actual, message, assertion)
        if operator == "ends_with":
            passed = text.endswith(expected)
            message = "" if passed else "response body does not end with expected text"
            return self._build_result("response_body", passed, expected, actual, message, assertion)
        if operator == "matches_regex":
            try:
                passed = re.search(expected, text) is not None
            except re.error as exc:
                return self._build_result("response_body", False, expected, actual, f"regex error: {exc}", assertion)
            message = "" if passed else "regex not matched"
            return self._build_result("response_body", passed, expected, actual, message, assertion)
        return self._build_result("response_body", False, expected, actual, f"unsupported operator: {operator}", assertion)

    def _run_header(self, response_result: dict, assertion: dict) -> dict[str, Any]:
        operator = assertion.get("operator")
        expected = str(assertion.get("expected") or "")
        header_name = str(assertion.get("header") or assertion.get("target") or "")
        headers = response_result.get("headers") or {}
        actual = ""
        if header_name:
            actual = str(headers.get(header_name) or headers.get(header_name.lower()) or "")
            if not actual:
                lowered = {str(k).lower(): v for k, v in headers.items()}
                actual = str(lowered.get(header_name.lower(), ""))
        if operator == "contains":
            passed = expected.lower() in actual.lower()
            message = "" if passed else f"header {header_name} missing expected content"
            return self._build_result("header", passed, expected, actual, message, assertion)
        if operator == "not_contains":
            passed = expected.lower() not in actual.lower()
            message = "" if passed else f"header {header_name} contains expected content"
            return self._build_result("header", passed, expected, actual, message, assertion)
        if operator == "==":
            passed = actual == expected
            message = "" if passed else f"header {header_name} {actual} != {expected}"
            return self._build_result("header", passed, expected, actual, message, assertion)
        if operator == "!=":
            passed = actual != expected
            message = "" if passed else f"header {header_name} {actual} == {expected}"
            return self._build_result("header", passed, expected, actual, message, assertion)
        if operator == "exists":
            passed = bool(actual)
            message = "" if passed else f"header {header_name} not found"
            return self._build_result("header", passed, expected, actual, message, assertion)
        if operator == "not_exists":
            passed = not bool(actual)
            message = "" if passed else f"header {header_name} should not exist"
            return self._build_result("header", passed, expected, actual, message, assertion)
        return self._build_result("header", False, expected, actual, f"unsupported operator: {operator}", assertion)

    def _compare_numeric(self, operator: str) -> Callable[[float, float], bool] | None:
        return {
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
        }.get(operator)

    def _to_number(self, value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return float(text) if "." in text else float(int(text))
            except ValueError:
                return None
        return None

    def _normalize_expected(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return value
        try:
            return json.loads(text)
        except Exception:
            return value

    def _sanitize_message(self, message: str) -> str:
        if not message:
            return ""
        cleaned = self._normalize_line_breaks(str(message))
        lines = [line.strip() for line in cleaned.split("\n")]
        filtered = [line for line in lines if line]
        return "\n".join(filtered)

    def _sanitize_value(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        cleaned = self._normalize_line_breaks(value)
        return "\n".join(line.rstrip() for line in cleaned.split("\n"))

    def _normalize_line_breaks(self, text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = (
            normalized.replace("\\r\\n", "\n").replace("\\r", "\n").replace("\\n", "\n")
        )
        normalized = normalized.replace("\t", " ").replace("\\t", " ")
        return normalized

    def _stringify_for_message(self, value: Any) -> str:
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    def _parse_range(self, value: Any) -> tuple[float, float] | None:
        text = str(value or "").strip()
        if not text:
            return None
        parts = re.split(r"\s*[~\-–—]\s*", text)
        if len(parts) != 2:
            return None
        lower = self._to_number(parts[0])
        upper = self._to_number(parts[1])
        if lower is None or upper is None:
            return None
        if lower <= upper:
            return lower, upper
        return upper, lower


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
