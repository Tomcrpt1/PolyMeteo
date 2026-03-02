from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class OutcomeBook:
    outcome: str
    token_id: str
    best_bid: float
    best_ask: float

    @property
    def mid(self) -> float:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return self.best_ask or self.best_bid


@dataclass(slots=True)
class LimitOrderRequest:
    token_id: str
    outcome: str
    price: float
    size_usd: float


@dataclass(slots=True)
class TradeDecision:
    should_trade: bool
    orders: list[LimitOrderRequest]
    reason: str
