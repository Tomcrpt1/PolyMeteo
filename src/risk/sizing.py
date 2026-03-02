from __future__ import annotations


def size_from_edge(edge: float, base_order_usd: float, max_order_usd: float) -> float:
    multiplier = min(2.0, max(0.25, edge / 0.05))
    return min(max_order_usd, base_order_usd * multiplier)
