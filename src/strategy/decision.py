from __future__ import annotations

from dataclasses import dataclass

from src.polymarket.models import LimitOrderRequest, OutcomeBook, TradeDecision
from src.strategy.buckets import adjacent_buckets


@dataclass(slots=True)
class DecisionConfig:
    edge_threshold: float
    max_order_usd: float


def decide_orders(
    model_probs: dict[str, float],
    market_books: dict[str, OutcomeBook],
    token_map: dict[str, str],
    late_peak_risk: float,
    cfg: DecisionConfig,
) -> TradeDecision:
    market_probs = {k: market_books[k].mid for k in model_probs if k in market_books}
    edges = {k: model_probs[k] - market_probs.get(k, 0.0) for k in model_probs}

    best = max(edges, key=edges.get)
    if edges[best] <= cfg.edge_threshold:
        return TradeDecision(should_trade=False, orders=[], reason="edge below threshold")

    selected = adjacent_buckets(best, radius=1)
    if late_peak_risk > 0.65:
        idx = min(len(selected) - 1, 2)
        selected[idx] = selected[-1]

    orders: list[LimitOrderRequest] = []
    per_order = cfg.max_order_usd / max(1, len(selected))
    for bucket in selected:
        book = market_books.get(bucket)
        token_id = token_map.get(bucket)
        if not book or not token_id:
            continue
        edge = edges.get(bucket, 0.0)
        if edge < cfg.edge_threshold / 2:
            continue
        price = min(0.99, max(0.01, book.best_bid + 0.01 if book.best_bid else book.mid))
        orders.append(LimitOrderRequest(token_id=token_id, outcome=bucket, price=price, size_usd=per_order))

    if not orders:
        return TradeDecision(should_trade=False, orders=[], reason="no qualifying adjacent buckets")
    return TradeDecision(should_trade=True, orders=orders, reason=f"best edge {best}={edges[best]:.3f}")
