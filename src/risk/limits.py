from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from src.polymarket.models import LimitOrderRequest


@dataclass(slots=True)
class RiskState:
    order_timestamps: list[datetime]


@dataclass(slots=True)
class RiskLimits:
    max_total_exposure_usd: float
    max_order_usd: float
    max_orders_per_hour: int


class RiskManager:
    def __init__(
        self,
        limits: RiskLimits,
        exposure_provider: Callable[[], float] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ):
        self.limits = limits
        self.state = RiskState(order_timestamps=[])
        self._exposure_provider = exposure_provider or (lambda: 0.0)
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def _now_utc(self) -> datetime:
        current = self._now_provider()
        if current.tzinfo is None:
            return current.replace(tzinfo=timezone.utc)
        return current.astimezone(timezone.utc)

    def _purge_old_order_timestamps(self, now_utc: datetime) -> None:
        cutoff = now_utc - timedelta(hours=1)
        self.state.order_timestamps = [ts for ts in self.state.order_timestamps if ts >= cutoff]

    def get_current_exposure_usd(self) -> float:
        return float(self._exposure_provider())

    def validate_order(self, order: LimitOrderRequest) -> tuple[bool, str]:
        now_utc = self._now_utc()
        self._purge_old_order_timestamps(now_utc)

        if order.size_usd > self.limits.max_order_usd:
            return False, "order exceeds max_order_usd"
        if self.get_current_exposure_usd() + order.size_usd > self.limits.max_total_exposure_usd:
            return False, "total exposure limit"
        if len(self.state.order_timestamps) >= self.limits.max_orders_per_hour:
            return False, "max_orders_per_hour reached"
        return True, "ok"

    def register_order(self, order: LimitOrderRequest) -> None:
        _ = order
        now_utc = self._now_utc()
        self._purge_old_order_timestamps(now_utc)
        self.state.order_timestamps.append(now_utc)
