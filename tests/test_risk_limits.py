from src.polymarket.models import LimitOrderRequest
from src.risk.limits import RiskLimits, RiskManager


def test_risk_limits_blocks_large_orders():
    rm = RiskManager(RiskLimits(max_total_exposure_usd=100, max_order_usd=10, max_orders_per_hour=3))
    ok, reason = rm.validate_order(LimitOrderRequest(token_id="1", outcome="15", price=0.2, size_usd=20))
    assert not ok
    assert "max_order" in reason


def test_risk_limits_orders_per_hour():
    rm = RiskManager(RiskLimits(max_total_exposure_usd=100, max_order_usd=50, max_orders_per_hour=1))
    order = LimitOrderRequest(token_id="1", outcome="15", price=0.2, size_usd=10)
    ok, _ = rm.validate_order(order)
    assert ok
    rm.register_order(order)
    ok2, reason2 = rm.validate_order(order)
    assert not ok2
    assert "per_hour" in reason2
