from __future__ import annotations

from dataclasses import dataclass

from src.polymarket.models import LimitOrderRequest


@dataclass(slots=True)
class RiskState:
    open_exposure_usd: float = 0.0
    orders_in_last_hour: int = 0


@dataclass(slots=True)
class RiskLimits:
    max_total_exposure_usd: float
    max_order_usd: float
    max_orders_per_hour: int


class RiskManager:
    def __init__(self, limits: RiskLimits):
        self.limits = limits
        self.state = RiskState()

    def validate_order(self, order: LimitOrderRequest) -> tuple[bool, str]:
        if order.size_usd > self.limits.max_order_usd:
            return False, "order exceeds max_order_usd"
        if self.state.open_exposure_usd + order.size_usd > self.limits.max_total_exposure_usd:
            return False, "total exposure limit"
        if self.state.orders_in_last_hour >= self.limits.max_orders_per_hour:
            return False, "max_orders_per_hour reached"
        return True, "ok"

    def register_order(self, order: LimitOrderRequest) -> None:
        self.state.open_exposure_usd += order.size_usd
        self.state.orders_in_last_hour += 1
