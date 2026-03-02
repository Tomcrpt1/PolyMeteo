from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


def now_tz(timezone: str) -> datetime:
    return datetime.now(ZoneInfo(timezone))


def parse_date(date_iso: str) -> date:
    return date.fromisoformat(date_iso)
