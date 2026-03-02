from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.polymarket.clob_client import PolymarketClient
from src.polymarket.models import LimitOrderRequest


@dataclass(slots=True)
class TraderState:
    open_orders: dict[str, LimitOrderRequest] = field(default_factory=dict)
    orders_placed_hour: int = 0


class Trader:
    def __init__(self, client: PolymarketClient):
        self.client = client
        self.state = TraderState()
        self.log = logging.getLogger("polymeteo")

    def requote(self, desired_orders: list[LimitOrderRequest]) -> list[str]:
        order_ids: list[str] = []
        for order in desired_orders:
            order_id = self.client.place_limit_order(order)
            self.state.open_orders[order_id] = order
            self.state.orders_placed_hour += 1
            order_ids.append(order_id)
        return order_ids

    def cancel_all(self) -> None:
        if self.state.open_orders:
            self.log.info("Cancelling %d paper/open orders", len(self.state.open_orders))
        self.state.open_orders.clear()
