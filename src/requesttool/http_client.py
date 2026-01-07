from __future__ import annotations

from typing import Any

import requests


def send_request(params: dict) -> dict:
    method = params.get("method")
    url = params.get("url")
    headers = params.get("headers")
    body = params.get("body")
    timeout = params.get("timeout")
    method = str(method).upper() if method is not None else None

    if not method:
        return {
            "success": False,
            "error_type": "InvalidMethod",
            "error_message": "method is required",
        }

    if method not in {"GET", "POST", "PUT", "DELETE"}:
        return {
            "success": False,
            "error_type": "InvalidMethod",
            "error_message": f"unsupported method: {method}",
        }

    if not url:
        return {
            "success": False,
            "error_type": "InvalidURL",
            "error_message": "url is required",
        }

    try:
        request_kwargs: dict[str, Any] = {
            "method": method,
            "url": url,
            "headers": headers,
            "timeout": timeout,
        }
        if method == "GET":
            request_kwargs["params"] = body
        else:
            request_kwargs["json"] = body

        response = requests.request(
            **request_kwargs,
        )
        if response.apparent_encoding:
            if response.encoding is None:
                response.encoding = response.apparent_encoding
            elif response.encoding.lower() in {"iso-8859-1", "latin-1"}:
                response.encoding = response.apparent_encoding
            elif response.encoding.lower() != response.apparent_encoding.lower():
                response.encoding = response.apparent_encoding
        response_text = response.text
        elapsed_ms = int(response.elapsed.total_seconds() * 1000)
        try:
            response_json = response.json()
        except ValueError:
            response_json = None
        return {
            "success": True,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "response_text": response_text,
            "response_json": response_json,
            "elapsed_ms": elapsed_ms,
        }
    except requests.exceptions.Timeout as exc:
        return {
            "success": False,
            "error_type": "Timeout",
            "error_message": str(exc),
        }
    except requests.exceptions.ConnectionError as exc:
        return {
            "success": False,
            "error_type": "ConnectionError",
            "error_message": str(exc),
        }
    except requests.RequestException as exc:
        return {
            "success": False,
            "error_type": "RequestException",
            "error_message": str(exc),
        }


if __name__ == "__main__":
    demo_params = {
        "method": "GET",
        "url": "https://httpbin.org/get",
        "headers": {"Accept": "application/json"},
        "body": {"demo": "ping"},
        "timeout": 10,
    }
    print(send_request(demo_params))
