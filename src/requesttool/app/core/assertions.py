from __future__ import annotations

import re
from typing import Any

from jsonpath_ng import parse


def build_result(
    name: str,
    passed: bool,
    actual: Any,
    expected: Any,
    message: str,
) -> dict:
    return {
        "name": name,
        "passed": bool(passed),
        "actual": actual,
        "expected": expected,
        "message": message,
    }


def assert_http_status(actual_status: int | None, expected_status: int) -> dict:
    if actual_status is None:
        return build_result("http_status", False, None, expected_status, "missing status code")
    passed = actual_status == expected_status
    message = "" if passed else f"status {actual_status} != {expected_status}"
    return build_result("http_status", passed, actual_status, expected_status, message)


def assert_jsonpath_equals(json_data: Any, path: str, expected: Any, name: str) -> dict:
    if json_data is None:
        return build_result(name, False, None, expected, "response json is empty")
    try:
        matches = [match.value for match in parse(path).find(json_data)]
    except Exception as exc:
        return build_result(name, False, None, expected, f"jsonpath error: {exc}")
    if not matches:
        return build_result(name, False, None, expected, f"path not found: {path}")
    actual = matches[0] if len(matches) == 1 else matches
    passed = actual == expected
    message = "" if passed else f"{path} {actual} != {expected}"
    return build_result(name, passed, actual, expected, message)


def parse_success_expectation(text: str) -> bool | None:
    if not text:
        return None
    normalized = text.lower()
    match = re.search(r"success\s*[:=]\s*(true|false|1|0)", normalized)
    if match:
        return match.group(1) in {"true", "1"}
    if "success" in normalized:
        if "false" in normalized or "0" in normalized:
            return False
        if "true" in normalized or "1" in normalized:
            return True
    return None
