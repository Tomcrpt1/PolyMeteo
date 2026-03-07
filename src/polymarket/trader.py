from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.polymarket.clob_client import PolymarketClient
from src.polymarket.models import LimitOrderRequest


@dataclass(slots=True)
class TraderState:
    open_orders: dict[str, LimitOrderRequest] = field(default_factory=dict)
    orders_placed_hour: int = 0


@dataclass(slots=True)
class ExecutionState:
    """Execution-grounded exposure state.

    In paper mode, fills are simulated as immediate and update this tracker.
    In live mode, this should be populated from exchange fills/positions.
    """

    lock19_main_exposure_usd: float = 0.0
    lock19_hedge_exposure_usd: float = 0.0
    legacy_exposure_usd: float = 0.0

    def register_lock19_fill(self, order: LimitOrderRequest, main_bucket: str | None) -> None:
        if main_bucket and order.outcome == main_bucket:
            self.lock19_main_exposure_usd += order.size_usd
        else:
            self.lock19_hedge_exposure_usd += order.size_usd

    def register_legacy_fill(self, order: LimitOrderRequest) -> None:
        self.legacy_exposure_usd += order.size_usd

    def exposure_for_mode(self, strategy_mode: str) -> float:
        if strategy_mode == "legacy":
            return self.legacy_exposure_usd
        return self.lock19_main_exposure_usd + self.lock19_hedge_exposure_usd


class Trader:
    def __init__(self, client: PolymarketClient):
        self.client = client
        self.state = TraderState()
        self.execution = ExecutionState()
        self.log = logging.getLogger("polymeteo")

    def requote(
        self,
        desired_orders: list[LimitOrderRequest],
        lock19_main_bucket: str | None = None,
        strategy_mode: str = "lock19",
    ) -> list[str]:
        order_ids: list[str] = []
        for order in desired_orders:
            order_id = self.client.place_limit_order(order)
            self.state.open_orders[order_id] = order
            self.state.orders_placed_hour += 1
            if self.client.mode == "paper":
                if strategy_mode == "legacy":
                    self.execution.register_legacy_fill(order)
                else:
                    self.execution.register_lock19_fill(order, lock19_main_bucket)
            order_ids.append(order_id)
        return order_ids

    def cancel_all(self) -> None:
        if self.state.open_orders:
            self.log.info("Cancelling %d paper/open orders", len(self.state.open_orders))
        self.state.open_orders.clear()
