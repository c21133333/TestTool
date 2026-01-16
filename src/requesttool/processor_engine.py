from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from jsonpath_ng import parse


TEMPLATE_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def render_template(value: str, variables: dict[str, Any]) -> str:
    def replacer(match: re.Match) -> str:
        key = match.group(1)
        return "" if key not in variables else str(variables.get(key))
    return TEMPLATE_PATTERN.sub(replacer, value)


def apply_templates(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return render_template(value, variables)
    if isinstance(value, list):
        return [apply_templates(item, variables) for item in value]
    if isinstance(value, dict):
        return {
            apply_templates(key, variables) if isinstance(key, str) else key: apply_templates(val, variables)
            for key, val in value.items()
        }
    return value


ProcessorHandler = Callable[[dict, dict], dict | None]


class ProcessorRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, ProcessorHandler] = {}

    def register(self, processor_type: str) -> Callable[[ProcessorHandler], ProcessorHandler]:
        def decorator(func: ProcessorHandler) -> ProcessorHandler:
            self._handlers[processor_type] = func
            return func
        return decorator

    def get(self, processor_type: str) -> ProcessorHandler | None:
        return self._handlers.get(processor_type)


registry = ProcessorRegistry()


def _resolve_config(processor: dict, context: dict) -> dict:
    raw_config = processor.get("config") or {}
    if not isinstance(raw_config, dict):
        return {}
    return apply_templates(raw_config, context.get("variables", {}))


def _resolve_script_payload(processor: dict) -> dict:
    config = processor.get("config") if isinstance(processor.get("config"), dict) else {}
    payload = dict(config)
    for key in ("language", "code"):
        if processor.get(key) is not None:
            payload[key] = processor.get(key)
    return payload


def _is_not_empty(value: Any) -> bool:
    return value not in (None, "", [])


def _execute_js_script(code: str, variables: dict, timeout_ms: int) -> dict:
    node_path = _find_node_binary()
    if not node_path:
        raise RuntimeError("node runtime is required for script processor")
    runner_path = Path(__file__).resolve().with_name("js_sandbox_runner.js")
    if not runner_path.exists():
        raise RuntimeError("js sandbox runner not found")
    payload = {
        "code": code,
        "variables": variables,
        "timeout": timeout_ms,
    }
    result = subprocess.run(
        [node_path, str(runner_path)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=max(0.2, timeout_ms / 1000 + 0.2),
        check=False,
    )
    if result.returncode != 0:
        error_text = (result.stderr or "").strip() or "script execution failed"
        raise RuntimeError(error_text)
    if not result.stdout.strip():
        return {"variables": variables, "logs": []}
    output = json.loads(result.stdout)
    if not isinstance(output, dict):
        raise RuntimeError("invalid script output")
    return output


def _find_node_binary() -> str | None:
    binary = "node.exe" if os.name == "nt" else "node"
    candidates = []
    exe_dir = Path(sys.executable).resolve().parent
    candidates.append(exe_dir / binary)
    module_dir = Path(__file__).resolve().parent
    candidates.append(module_dir / binary)
    candidates.append(module_dir.parent / binary)
    candidates.append(module_dir.parents[1] / binary)
    project_root = module_dir.parents[2] if len(module_dir.parents) > 2 else module_dir.parent
    candidates.append(project_root / "third_party" / "node" / binary)
    candidates.append(Path.cwd() / binary)
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return shutil.which("node")


@registry.register("set_variable")
def _set_variable(processor: dict, context: dict) -> dict | None:
    config = _resolve_config(processor, context)
    key = str(config.get("key") or "").strip()
    if not key:
        return None
    value = config.get("value")
    context["variables"][key] = value
    return {"key": key, "value": value}


@registry.register("builtin_function")
def _builtin_function(processor: dict, context: dict) -> dict | None:
    config = _resolve_config(processor, context)
    target = str(config.get("target") or "").strip()
    if not target:
        return None
    func = config.get("function") or "timestamp"
    if func == "random":
        value = str(random.randint(100000, 999999))
    elif func == "uuid":
        value = str(uuid.uuid4())
    else:
        value = str(int(time.time() * 1000))
    context["variables"][target] = value
    return {"target": target, "value": value, "function": func}


@registry.register("sleep")
def _sleep(processor: dict, context: dict) -> dict | None:
    config = _resolve_config(processor, context)
    duration = config.get("milliseconds")
    try:
        duration_ms = max(0, int(duration))
    except Exception:
        duration_ms = 0
    if duration_ms > 0:
        time.sleep(duration_ms / 1000)
    return {"milliseconds": duration_ms}


@registry.register("jsonpath_extract")
def _jsonpath_extract(processor: dict, context: dict) -> dict | None:
    config = _resolve_config(processor, context)
    path = str(config.get("path") or "").strip()
    target = str(config.get("target") or "").strip()
    if not path or not target:
        return None
    response = context.get("response") or {}
    json_data = response.get("response_json")
    if json_data is None:
        return None
    try:
        matches = [match.value for match in parse(path).find(json_data)]
    except Exception:
        return None
    if not matches:
        return None
    value = matches[0] if len(matches) == 1 else matches
    context["variables"][target] = value
    return {"path": path, "target": target, "value": value}


@registry.register("regex_extract")
def _regex_extract(processor: dict, context: dict) -> dict | None:
    config = _resolve_config(processor, context)
    pattern = str(config.get("pattern") or "").strip()
    target = str(config.get("target") or "").strip()
    if not pattern or not target:
        return None
    response = context.get("response") or {}
    text = response.get("response_text") or ""
    if not text and response.get("response_json") is not None:
        text = json.dumps(response.get("response_json"), ensure_ascii=False)
    try:
        match = re.search(pattern, text)
    except re.error:
        return None
    if not match:
        return None
    group_index = config.get("group", 1)
    try:
        value = match.group(int(group_index))
    except Exception:
        value = match.group(0)
    context["variables"][target] = value
    return {"pattern": pattern, "group": group_index, "target": target, "value": value}


@registry.register("fail_if")
def _fail_if(processor: dict, context: dict) -> dict | None:
    config = _resolve_config(processor, context)
    variable = str(config.get("variable") or "").strip()
    operator = config.get("operator") or "exists"
    expected = config.get("value")
    if not variable:
        return None
    actual = context.get("variables", {}).get(variable)
    passed = True
    if operator == "exists":
        passed = actual is not None
    elif operator == "not_empty":
        passed = _is_not_empty(actual)
    elif operator == "equals":
        expected_value = expected
        passed = actual == expected_value
    if not passed:
        context["abort"] = True
        context["failure_message"] = f"post processor condition failed: {variable}"
        context["failure_expected"] = expected
        context["failure_actual"] = actual
        context["failure_target"] = variable
    return {
        "variable": variable,
        "operator": operator,
        "expected": expected,
        "actual": actual,
        "passed": passed,
    }


@registry.register("script")
def _script_processor(processor: dict, context: dict) -> dict | None:
    payload = _resolve_script_payload(processor)
    language = str(payload.get("language") or "js").lower()
    code = str(payload.get("code") or "")
    if not code.strip():
        return None
    if language not in {"js", "javascript"}:
        raise RuntimeError(f"unsupported script language: {language}")
    variables = context.get("variables", {})
    if not isinstance(variables, dict):
        variables = {}
        context["variables"] = variables
    before = dict(variables)
    output = _execute_js_script(code, dict(variables), 1000)
    new_vars = output.get("variables")
    logs = output.get("logs") if isinstance(output.get("logs"), list) else []
    if isinstance(new_vars, dict):
        variables.clear()
        variables.update(new_vars)
    for entry in logs:
        context["logs"].append(f"script_log={entry}")
    updated = {key: value for key, value in variables.items() if before.get(key) != value}
    removed = [key for key in before.keys() if key not in variables]
    result = {
        "language": "js",
        "updated": updated,
    }
    if removed:
        result["removed"] = removed
    if logs:
        result["logs"] = logs
    return result


def _apply_processors(processors: list, context: dict, phase: str) -> None:
    results = context.setdefault("processor_results", [])
    for processor in processors:
        if not isinstance(processor, dict):
            continue
        processor_type = processor.get("type") or ""
        enabled = processor.get("enabled", True) is not False
        resolved_config = _resolve_config(processor, context)
        result = {
            "phase": phase,
            "type": processor_type,
            "enabled": enabled,
            "config": resolved_config,
        }
        if not enabled:
            result["status"] = "disabled"
            results.append(result)
            continue
        handler = registry.get(processor_type)
        if handler is None:
            result["status"] = "unsupported"
            results.append(result)
            context["logs"].append(f"processor_unsupported={processor_type}")
            continue
        try:
            output = handler(processor, context)
            if output is not None:
                result["output"] = output
            if context.get("abort"):
                result["status"] = "failed"
                result["message"] = context.get("failure_message") or ""
            else:
                result["status"] = "ok"
            results.append(result)
        except Exception as exc:
            result["status"] = "error"
            result["message"] = str(exc)
            results.append(result)
            context["logs"].append(f"processor_error={processor_type}")
        if context.get("abort"):
            break


def _join_url(base_url: str, endpoint: str) -> str:
    if not endpoint:
        return base_url
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        return endpoint
    if not base_url:
        return endpoint
    return f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"


def _build_request_payload(request_data: dict, variables: dict) -> dict:
    payload = {
        "method": request_data.get("method"),
        "url": request_data.get("url"),
        "headers": request_data.get("headers") or {},
        "body": request_data.get("body"),
        "timeout": request_data.get("timeout"),
    }
    payload = apply_templates(payload, variables)
    base_url = request_data.get("base_url") or request_data.get("baseUrl")
    if isinstance(base_url, str):
        base_url = render_template(base_url, variables)
    else:
        base_url = (
            variables.get("baseUrl")
            or variables.get("base_url")
            or variables.get("baseurl")
        )
    url = payload.get("url")
    if isinstance(url, str) and url:
        payload["url"] = _join_url(str(base_url or ""), url)
    method = payload.get("method")
    if isinstance(method, str):
        payload["method"] = method.upper()
    if payload.get("headers") is None:
        payload["headers"] = {}
    if payload.get("body") is None:
        payload.pop("body", None)
    if payload.get("timeout") is None:
        payload["timeout"] = 20
    return payload


def execute_request(
    request_data: dict,
    assertions: list,
    pre_processors: list,
    post_processors: list,
    http_client,
    assertion_engine,
) -> tuple[dict, list[dict], dict]:
    initial_vars = request_data.get("variables") if isinstance(request_data, dict) else None
    if not isinstance(initial_vars, dict):
        initial_vars = request_data.get("vars") if isinstance(request_data, dict) else None
    if not isinstance(initial_vars, dict):
        initial_vars = {}
    context = {
        "variables": dict(initial_vars),
        "logs": [],
        "abort": False,
        "processor_results": [],
    }
    _apply_processors(pre_processors or [], context, "pre")
    payload = _build_request_payload(request_data, context["variables"])
    context["request_payload"] = payload
    response = http_client.send_request(payload)
    assertion_results: list[dict] = []
    if response.get("success") is True:
        assertion_results = assertion_engine.run_assertions(response, assertions)
    context["response"] = response
    context["assertions"] = assertion_results
    _apply_processors(post_processors or [], context, "post")
    if context.get("abort"):
        failure_message = context.get("failure_message") or "post processor aborted"
        response = dict(response)
        response["success"] = False
        response["error_type"] = "PostProcessorAbort"
        response["error_message"] = failure_message
        assertion_results = list(assertion_results)
        assertion_results.append(
            {
                "type": "post_processor",
                "result": "FAIL",
                "expected": context.get("failure_expected"),
                "actual": context.get("failure_actual"),
                "message": failure_message,
                "operator": "condition",
                "target": context.get("failure_target"),
            }
        )
    response = dict(response)
    response["request_headers"] = payload.get("headers") or {}
    response["request_body"] = payload.get("body")
    response["request_url"] = payload.get("url")
    response["processor_results"] = context.get("processor_results", [])
    return response, assertion_results, context


def execute_case(case: dict, http_client, assertion_engine) -> dict:
    request_data = case.get("request", {}) if isinstance(case, dict) else {}
    assertions = case.get("assertions", []) if isinstance(case, dict) else []
    pre_processors = case.get("preProcessors", []) if isinstance(case, dict) else []
    post_processors = case.get("postProcessors", []) if isinstance(case, dict) else []
    response, assertion_results, context = execute_request(
        request_data,
        assertions,
        pre_processors,
        post_processors,
        http_client,
        assertion_engine,
    )
    if response.get("success") is False:
        result = "FAIL"
    else:
        passed = all(item.get("result") == "PASS" for item in assertion_results)
        result = "PASS" if passed else "FAIL"
    return {
        "case_id": case.get("case_id"),
        "name": case.get("name"),
        "request": request_data,
        "assertions": assertions,
        "response": response,
        "assertion_results": assertion_results,
        "result": result,
        "logs": context.get("logs", []),
        "db_assertions": [],
        "attachments": [],
    }
