import requests

from requesttool import http_client


class _Elapsed:
    def __init__(self, seconds: float) -> None:
        self._seconds = seconds

    def total_seconds(self) -> float:
        return self._seconds


class _Response:
    def __init__(self, status_code: int, text: str, headers: dict, json_data=None) -> None:
        self.status_code = status_code
        self.text = text
        self.headers = headers
        self._json_data = json_data
        self.elapsed = _Elapsed(0.123)

    def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


def test_invalid_method():
    result = http_client.send_request({"method": "PATCH", "url": "http://x"})
    assert result["success"] is False
    assert result["error_type"] == "InvalidMethod"


def test_invalid_url():
    result = http_client.send_request({"method": "GET", "url": ""})
    assert result["success"] is False
    assert result["error_type"] == "InvalidURL"


def test_send_request_get_params(monkeypatch):
    called = {}

    def fake_request(**kwargs):
        called.update(kwargs)
        return _Response(200, "ok", {"X": "1"}, {"ok": True})

    monkeypatch.setattr(http_client.requests, "request", fake_request)
    result = http_client.send_request({"method": "get", "url": "http://x", "body": {"a": 1}})
    assert result["success"] is True
    assert called.get("params") == {"a": 1}
    assert "json" not in called


def test_send_request_post_json(monkeypatch):
    called = {}

    def fake_request(**kwargs):
        called.update(kwargs)
        return _Response(200, "ok", {"X": "1"}, {"ok": True})

    monkeypatch.setattr(http_client.requests, "request", fake_request)
    result = http_client.send_request({"method": "post", "url": "http://x", "body": {"a": 1}})
    assert result["success"] is True
    assert called.get("json") == {"a": 1}


def test_timeout_error(monkeypatch):
    def fake_request(**kwargs):
        raise requests.exceptions.Timeout("timeout")

    monkeypatch.setattr(http_client.requests, "request", fake_request)
    result = http_client.send_request({"method": "GET", "url": "http://x"})
    assert result["success"] is False
    assert result["error_type"] == "Timeout"
