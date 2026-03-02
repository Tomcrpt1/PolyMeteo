from src.polymarket.models import OutcomeBook
from src.strategy.decision import DecisionConfig, decide_orders


def test_decision_places_orders_when_edge_positive():
    model = {"<=12": 0.05, "13": 0.1, "14": 0.2, "15": 0.3, "16": 0.2, "17": 0.08, "18": 0.04, "19": 0.02, ">=20": 0.01}
    books = {k: OutcomeBook(outcome=k, token_id=f"t-{k}", best_bid=0.05, best_ask=0.08) for k in model}
    books["15"] = OutcomeBook(outcome="15", token_id="t-15", best_bid=0.15, best_ask=0.16)
    token_map = {k: f"t-{k}" for k in model}

    decision = decide_orders(model, books, token_map, late_peak_risk=0.2, cfg=DecisionConfig(edge_threshold=0.05, max_order_usd=30))
    assert decision.should_trade
    assert len(decision.orders) >= 1


def test_decision_no_trade_if_no_edge():
    model = {k: 1 / 9 for k in ["<=12", "13", "14", "15", "16", "17", "18", "19", ">=20"]}
    books = {k: OutcomeBook(outcome=k, token_id=f"t-{k}", best_bid=0.1, best_ask=0.12) for k in model}
    token_map = {k: f"t-{k}" for k in model}
    decision = decide_orders(model, books, token_map, late_peak_risk=0.2, cfg=DecisionConfig(edge_threshold=0.1, max_order_usd=30))
    assert not decision.should_trade
