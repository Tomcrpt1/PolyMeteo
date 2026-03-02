from __future__ import annotations

from datetime import datetime

from src.polymarket.markets import map_temp_to_bucket
from src.strategy.buckets import normalize_distribution


def update_intraday_distribution(
    prior: dict[str, float],
    max_observed_c: int,
    now_local: datetime,
    late_peak_risk: float,
    peak_hour_local: int = 15,
) -> dict[str, float]:
    updated = prior.copy()
    floor_bucket = map_temp_to_bucket(max_observed_c)
    floor_reached = False
    for bucket in list(updated.keys()):
        if bucket == floor_bucket:
            floor_reached = True
        if not floor_reached:
            updated[bucket] = 0.0

    hour = now_local.hour + now_local.minute / 60
    if hour > peak_hour_local:
        decay = min(0.9, (hour - peak_hour_local) / 8)
        for bucket in updated:
            if bucket in {"<=12", floor_bucket}:
                continue
            updated[bucket] *= max(0.1, 1 - decay * (1 - late_peak_risk))

    return normalize_distribution(updated)
