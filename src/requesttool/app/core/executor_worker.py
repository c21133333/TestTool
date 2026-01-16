from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests
from PySide6.QtCore import QObject, Signal

from requesttool.app.core import assertions as assertion_core


def _join_url(base_url: str, endpoint: str) -> str:
    if not endpoint:
        return base_url
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        return endpoint
    if not base_url:
        return endpoint
    return f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"


def _resolve_version(endpoint: str, env_vars: dict, request_json: dict) -> str:
    if "{version}" not in endpoint:
        return endpoint
    version = env_vars.get("version")
    if version is None:
        path_info = request_json.get("path") if isinstance(request_json.get("path"), dict) else {}
        version = path_info.get("version") if isinstance(path_info, dict) else None
    if version is None:
        return endpoint
    return endpoint.replace("{version}", str(version))


def _normalize_headers(env_headers: dict, case_headers: dict) -> dict:
    merged = {}
    if isinstance(env_headers, dict):
        merged.update(env_headers)
    if isinstance(case_headers, dict):
        merged.update(case_headers)
    if "Content-Type" not in merged and "content-type" not in merged:
        merged["Content-Type"] = "application/json"
    return merged


def _resolve_request_payload(case: dict, env: dict) -> dict:
    request_json = {}
    if isinstance(case.get("request_json"), dict):
        request_json = case.get("request_json", {})
    elif isinstance(case.get("request"), dict):
        request_json = case.get("request", {})
    endpoint = case.get("endpoint") or request_json.get("endpoint") or request_json.get("url") or case.get("url") or ""
    env_vars = env.get("vars") if isinstance(env.get("vars"), dict) else {}
    endpoint = _resolve_version(str(endpoint), env_vars, request_json)
    base_url = env.get("baseUrl") or env.get("base_url") or ""
    url = _join_url(str(base_url), str(endpoint))
    method = request_json.get("method") or case.get("method") or "POST"
    headers = _normalize_headers(env.get("headers", {}), case.get("headers", {}) or request_json.get("headers", {}))
    params = case.get("params") or request_json.get("params") or request_json.get("query")
    body = case.get("body")
    if body is None:
        body = request_json.get("body")
    if body is None:
        body = request_json.get("data")
    timeout = request_json.get("timeout") or 20
    return {
        "method": str(method).upper(),
        "url": url,
        "headers": headers,
        "params": params,
        "body": body,
        "timeout": timeout,
    }


def _send_request(payload: dict) -> dict:
    method = payload.get("method")
    url = payload.get("url")
    headers = payload.get("headers") or {}
    params = payload.get("params")
    body = payload.get("body")
    timeout = payload.get("timeout") or 20
    start = time.monotonic()
    try:
        request_kwargs: dict[str, Any] = {
            "method": method,
            "url": url,
            "headers": headers,
            "timeout": timeout,
        }
        if params:
            request_kwargs["params"] = params
        if method == "GET":
            pass
        else:
            if isinstance(body, (dict, list)):
                request_kwargs["json"] = body
            elif body is not None:
                request_kwargs["data"] = body
        response = requests.request(**request_kwargs)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        try:
            response_json = response.json()
        except ValueError:
            response_json = None
        return {
            "success": True,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "response_text": response.text,
            "response_json": response_json,
            "elapsed_ms": elapsed_ms,
            "request_headers": headers,
            "request_body": body,
        }
    except requests.exceptions.Timeout as exc:
        return _build_error("Timeout", str(exc), headers, body, start)
    except requests.exceptions.ConnectionError as exc:
        return _build_error("ConnectionError", str(exc), headers, body, start)
    except requests.RequestException as exc:
        return _build_error("RequestException", str(exc), headers, body, start)


def _build_error(error_type: str, message: str, headers: dict, body: object, start: float) -> dict:
    elapsed_ms = int((time.monotonic() - start) * 1000)
    return {
        "success": False,
        "error_type": error_type,
        "error_message": message,
        "elapsed_ms": elapsed_ms,
        "request_headers": headers,
        "request_body": body,
    }

def _is_ai_assertion_enabled(
    assertions: object,
    assertion_type: str,
    path: str | None = None,
    expected: object | None = None,
    operator: str | None = "==",
) -> bool:
    if not isinstance(assertions, list):
        return True
    matched = False
    normalized_expected = _normalize_expected(expected)
    for row in assertions:
        if not isinstance(row, dict):
            continue
        if row.get("type") != assertion_type:
            continue
        target = row.get("path") or row.get("target") or row.get("header") or ""
        if path and target and target != path:
            continue
        if operator:
            row_operator = row.get("operator") or "=="
            if row_operator != operator:
                continue
        if expected is not None:
            row_expected = _normalize_expected(row.get("expected"))
            if row_expected != normalized_expected:
                continue
        matched = True
        if row.get("enabled", True) is True:
            return True
    if matched:
        return False
    return False


def _build_assertions(case: dict, response: dict) -> list[dict]:
    results: list[dict] = []
    assertion_rows = case.get("assertions")
    expected_status = case.get("expected_http_status")
    if expected_status is not None and _is_ai_assertion_enabled(
        assertion_rows, "status_code", expected=expected_status
    ):
        try:
            expected_status_value = int(expected_status)
        except (TypeError, ValueError):
            expected_status_value = None
        if expected_status_value is not None:
            results.append(
                assertion_core.assert_http_status(
                    response.get("status_code"),
                    expected_status_value,
                )
            )
    expected_code = _normalize_expected(case.get("expected_business_code"))
    if expected_code not in (None, "", "N/A", "n/a") and _is_ai_assertion_enabled(
        assertion_rows, "json_path", "$.code", expected=expected_code
    ):
        results.append(
            assertion_core.assert_jsonpath_equals(
                response.get("response_json"),
                "$.code",
                expected_code,
                "business_code",
            )
        )
    success_expected = assertion_core.parse_success_expectation(case.get("assertion_points") or "")
    if success_expected is not None and _is_ai_assertion_enabled(
        assertion_rows, "json_path", "$.success", expected=success_expected
    ):
        results.append(
            assertion_core.assert_jsonpath_equals(
                response.get("response_json"),
                "$.success",
                success_expected,
                "success",
            )
        )
    return results


def _normalize_expected(value: Any) -> Any:
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return ""
        lowered = text.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            return int(text)
        except ValueError:
            return text
    return value


def _evaluate_result(response: dict, assertions: list[dict]) -> tuple[str, str]:
    if response.get("success") is not True:
        return "NG", response.get("error_message") or "request failed"
    failed = [item for item in assertions if not item.get("passed")]
    if failed:
        return "NG", failed[0].get("message") or "assertion failed"
    return "OK", ""


@dataclass
class RunResult:
    summary: dict
    items: list[dict]
    duration_ms: int
    canceled: bool


class SuiteExecutorWorker(QObject):
    progress = Signal(int, int)
    case_started = Signal(object)
    case_finished = Signal(object)
    finished = Signal(object)

    def __init__(self, suite: dict, env: dict) -> None:
        super().__init__()
        self._suite = suite
        self._env = env
        self._canceled = False

    def cancel(self) -> None:
        self._canceled = True

    def run(self) -> None:
        start = time.monotonic()
        cases = self._suite.get("cases") or []
        results: list[dict] = []
        total = len(cases)
        for idx, case in enumerate(cases, start=1):
            if self._canceled:
                break
            self.case_started.emit(case)
            payload = _resolve_request_payload(case, self._env)
            response = _send_request(payload)
            assertions = _build_assertions(case, response)
            result, failure_reason = _evaluate_result(response, assertions)
            result_item = {
                "case_id": case.get("case_id"),
                "name": case.get("name"),
                "category": case.get("category", ""),
                "request": payload,
                "response": response,
                "assertions": assertions,
                "elapsed_ms": response.get("elapsed_ms"),
                "result": result,
                "failure_reason": failure_reason,
            }
            results.append(result_item)
            self.case_finished.emit(result_item)
            self.progress.emit(idx, total)
        duration_ms = int((time.monotonic() - start) * 1000)
        summary = build_summary(results, duration_ms)
        self.finished.emit(RunResult(summary, results, duration_ms, self._canceled))


def build_summary(items: list[dict], duration_ms: int) -> dict:
    total = len(items)
    ok = sum(1 for item in items if item.get("result") == "OK")
    ng = total - ok
    pass_rate = round((ok / total) * 100, 2) if total else 0.0
    return {
        "total": total,
        "ok": ok,
        "ng": ng,
        "pass_rate": pass_rate,
        "duration_ms": duration_ms,
    }
