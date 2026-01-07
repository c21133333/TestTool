from __future__ import annotations

from typing import Any


def _get_by_path(data: Any, path: str) -> Any:
    if path == "$":
        return data
    if not path.startswith("$."):
        raise ValueError("JSONPath must start with $.")
    parts = [p for p in path[2:].split(".") if p]
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(f"Path not found: {path}")
    return current


def evaluate_assertions(response_result: dict, assertions: list[dict]) -> list[dict]:
    results: list[dict] = []
    for assertion in assertions:
        kind = assertion.get("type")
        passed = False
        reason = ""
        try:
            if kind == "status_code_equals":
                expected = assertion.get("expected")
                actual = response_result.get("status_code")
                passed = actual == expected
                if not passed:
                    reason = f"status_code {actual} != {expected}"
            elif kind == "jsonpath_equals":
                path = assertion.get("path")
                expected = assertion.get("expected")
                actual = _get_by_path(response_result.get("response_json"), path)
                passed = actual == expected
                if not passed:
                    reason = f"{path} {actual} != {expected}"
            elif kind == "jsonpath_not_empty":
                path = assertion.get("path")
                value = _get_by_path(response_result.get("response_json"), path)
                passed = value not in (None, "", [], {})
                if not passed:
                    reason = f"{path} is empty"
            else:
                reason = f"Unknown assertion type: {kind}"
        except Exception as exc:
            passed = False
            reason = str(exc)

        results.append(
            {
                "type": kind,
                "pass": passed,
                "reason": reason,
            }
        )

    return results
