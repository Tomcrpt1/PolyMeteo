from datetime import datetime, timedelta, timezone

from src.polymarket.models import LimitOrderRequest
from src.risk.limits import RiskLimits, RiskManager


def test_risk_limits_blocks_large_orders():
    rm = RiskManager(RiskLimits(max_total_exposure_usd=100, max_order_usd=10, max_orders_per_hour=3))
    ok, reason = rm.validate_order(LimitOrderRequest(token_id="1", outcome="15", price=0.2, size_usd=20))
    assert not ok
    assert "max_order" in reason


def test_risk_limits_orders_per_hour_rolling_window():
    now = datetime(2026, 3, 5, 12, 0, tzinfo=timezone.utc)

    def _now_provider() -> datetime:
        return now

    rm = RiskManager(RiskLimits(max_total_exposure_usd=100, max_order_usd=50, max_orders_per_hour=2), now_provider=_now_provider)
    order = LimitOrderRequest(token_id="1", outcome="15", price=0.2, size_usd=10)

    ok1, _ = rm.validate_order(order)
    assert ok1
    rm.register_order(order)

    now = now + timedelta(minutes=30)
    ok2, _ = rm.validate_order(order)
    assert ok2
    rm.register_order(order)

    now = now + timedelta(minutes=20)
    ok3, reason3 = rm.validate_order(order)
    assert not ok3
    assert "per_hour" in reason3

    now = now + timedelta(minutes=11)
    ok4, _ = rm.validate_order(order)
    assert ok4


def test_risk_exposure_uses_provider_not_order_counter():
    exposure = {"usd": 0.0}
    rm = RiskManager(
        RiskLimits(max_total_exposure_usd=100, max_order_usd=50, max_orders_per_hour=10),
        exposure_provider=lambda: exposure["usd"],
    )
    order = LimitOrderRequest(token_id="1", outcome="15", price=0.2, size_usd=30)

    ok1, _ = rm.validate_order(order)
    assert ok1

    # Registering an order should not itself increase exposure.
    rm.register_order(order)
    ok2, _ = rm.validate_order(order)
    assert ok2

    # Once exposure source of truth moves (simulated fill/position update), risk reflects it.
    exposure["usd"] = 80.0
    ok3, reason3 = rm.validate_order(order)
    assert not ok3
    assert "total exposure" in reason3


def test_risk_exposure_live_placeholder_unfilled_order_does_not_increase_exposure():
    rm = RiskManager(
        RiskLimits(max_total_exposure_usd=25, max_order_usd=25, max_orders_per_hour=10),
        exposure_provider=lambda: 0.0,
    )
    order = LimitOrderRequest(token_id="1", outcome="15", price=0.2, size_usd=20)

    ok1, _ = rm.validate_order(order)
    assert ok1
    rm.register_order(order)

    # Exposure provider remains unchanged; risk should still treat exposure as zero-filled.
    ok2, _ = rm.validate_order(order)
    assert ok2


def test_validate_batch_enforces_exposure_across_orders_in_same_cycle():
    rm = RiskManager(
        RiskLimits(max_total_exposure_usd=50, max_order_usd=20, max_orders_per_hour=10),
        exposure_provider=lambda: 40.0,
    )
    orders = [
        LimitOrderRequest(token_id="1", outcome="15", price=0.2, size_usd=10),
        LimitOrderRequest(token_id="2", outcome="16", price=0.2, size_usd=10),
    ]

    approved, blocked = rm.validate_batch(orders)

    assert approved == [orders[0]]
    assert len(blocked) == 1
    assert blocked[0][0] == orders[1]
    assert "total exposure" in blocked[0][1]


def test_validate_batch_enforces_per_hour_capacity_across_orders_in_same_cycle():
    now = datetime(2026, 3, 5, 12, 0, tzinfo=timezone.utc)

    def _now_provider() -> datetime:
        return now

    rm = RiskManager(
        RiskLimits(max_total_exposure_usd=100, max_order_usd=20, max_orders_per_hour=2),
        now_provider=_now_provider,
    )
    rm.state.order_timestamps = [now - timedelta(minutes=10)]
    orders = [
        LimitOrderRequest(token_id="1", outcome="15", price=0.2, size_usd=10),
        LimitOrderRequest(token_id="2", outcome="16", price=0.2, size_usd=10),
    ]

    approved, blocked = rm.validate_batch(orders)

    assert approved == [orders[0]]
    assert len(blocked) == 1
    assert blocked[0][0] == orders[1]
    assert "per_hour" in blocked[0][1]
