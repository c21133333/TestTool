from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


BEIJING_TIMEZONE = ZoneInfo("Asia/Shanghai")


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_beijing_datetime(value: datetime) -> datetime:
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(BEIJING_TIMEZONE)


def to_beijing_isoformat(value: datetime) -> str:
    return to_beijing_datetime(value).isoformat()


def beijing_now_isoformat() -> str:
    return to_beijing_isoformat(utc_now())
