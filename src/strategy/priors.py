from __future__ import annotations

import math

from src.polymarket.markets import BUCKETS
from src.strategy.buckets import normalize_distribution


def gaussian_prior(forecast_tmax_c: float, sigma_c: float) -> dict[str, float]:
    raw: dict[str, float] = {}
    for bucket in BUCKETS:
        if bucket == "<=12":
            x = 12
        elif bucket == ">=20":
            x = 20
        else:
            x = int(bucket)
        z = (x - forecast_tmax_c) / sigma_c
        raw[bucket] = math.exp(-0.5 * z * z)
    return normalize_distribution(raw)
