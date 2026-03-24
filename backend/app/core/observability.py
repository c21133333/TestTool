from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import UTC, date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.app.core.config import settings

_request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
_component_context: ContextVar[str] = ContextVar("component", default="app")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _serialize_log_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _serialize_log_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_log_value(item) for item in value]
    return str(value)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": _utc_now().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "component": getattr(record, "component", _component_context.get()),
            "request_id": getattr(record, "request_id", _request_id_context.get()),
        }
        event = getattr(record, "event", None)
        if event:
            payload["event"] = event
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(_serialize_log_value(fields))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(*, component: str) -> None:
    logger = logging.getLogger("eazytest")
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    existing_handler = next(
        (handler for handler in logger.handlers if getattr(handler, "name", "") == "eazytest-json"),
        None,
    )
    if existing_handler is None:
        handler = logging.StreamHandler(sys.stdout)
        handler.name = "eazytest-json"
        handler.setFormatter(JsonLogFormatter())
        logger.handlers.clear()
        logger.addHandler(handler)
    _component_context.set(component)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"eazytest.{name}")


def bind_request_context(request_id: str | None = None) -> Token[str | None]:
    resolved_request_id = request_id or uuid4().hex
    return _request_id_context.set(resolved_request_id)


def clear_request_context(token: Token[str | None]) -> None:
    _request_id_context.reset(token)


def get_request_id() -> str | None:
    return _request_id_context.get()


def log_event(logger: logging.Logger, event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    logger.log(
        level,
        event,
        extra={
            "event": event,
            "fields": fields,
            "request_id": get_request_id(),
            "component": _component_context.get(),
        },
    )
