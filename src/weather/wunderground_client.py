from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

from src.utils.retry import network_retry


@dataclass(slots=True)
class WundergroundReading:
    fetched_at: datetime
    high_so_far_c: int | None
    raw_excerpt: str | None = None


class WundergroundClient:
    """Best-effort parser for WU daily history page; use sparingly due to fragility."""

    def __init__(self, url: str, min_poll_seconds: int = 3600):
        self.url = url
        self.min_poll_seconds = min_poll_seconds
        self.client = httpx.Client(timeout=20)
        self._cached: WundergroundReading | None = None

    def reset_cache(self) -> None:
        self._cached = None

    @network_retry
    def fetch_daily_high_so_far(self) -> WundergroundReading:
        now = datetime.utcnow()
        if self._cached and (now - self._cached.fetched_at) < timedelta(seconds=self.min_poll_seconds):
            return self._cached

        res = self.client.get(self.url)
        res.raise_for_status()
        text = res.text
        # Heuristic parser to avoid brittle full DOM dependencies.
        match = re.search(r'"temperatureMax":\{"value":(-?\d+\.?\d*)', text)
        value = int(round(float(match.group(1)))) if match else None
        reading = WundergroundReading(fetched_at=now, high_so_far_c=value, raw_excerpt=match.group(0) if match else None)
        self._cached = reading
        return reading
