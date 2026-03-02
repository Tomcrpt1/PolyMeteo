from __future__ import annotations

from src.polymarket.markets import BUCKETS


def normalize_distribution(values: dict[str, float]) -> dict[str, float]:
    total = sum(max(v, 0.0) for v in values.values())
    if total <= 0:
        uniform = 1 / len(BUCKETS)
        return {k: uniform for k in BUCKETS}
    return {k: max(values.get(k, 0.0), 0.0) / total for k in BUCKETS}


def adjacent_buckets(center: str, radius: int = 1) -> list[str]:
    idx = BUCKETS.index(center)
    lo = max(0, idx - radius)
    hi = min(len(BUCKETS), idx + radius + 1)
    return BUCKETS[lo:hi]
