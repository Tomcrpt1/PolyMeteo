from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from src.main import (
    BotSession,
    PollingState,
    RuntimeState,
    maybe_rollover_session,
    resolve_active_target_date,
    run_scheduled_cycle,
    sync_lock19_exposure_from_execution,
)
from src.polymarket.models import LimitOrderRequest
from src.polymarket.trader import Trader
from src.risk.limits import RiskLimits, RiskManager
from src.strategy.lock19 import Lock19Inputs, decide_lock19
from src.weather.models import HourlyWeatherRecord, WeatherConditions


TZ = ZoneInfo("Europe/Paris")


class FakeWeatherClient:
    def __init__(self):
        self.calls = 0

    def fetch_hourly_conditions(self, target_date, latitude, longitude, timezone):
        self.calls += 1
        now = datetime(2026, 3, 5, 12, 0, tzinfo=TZ)
        records = [
            HourlyWeatherRecord(timestamp=datetime(2026, 3, 5, 10, 0, tzinfo=TZ), temperature_c=15.2, wind_kph=5, cloud_cover_pct=20),
            HourlyWeatherRecord(timestamp=datetime(2026, 3, 5, 11, 0, tzinfo=TZ), temperature_c=16.1, wind_kph=6, cloud_cover_pct=30),
        ]
        return WeatherConditions(last_updated=now, current_temp_c=16.1, max_temp_so_far_c=16.1, max_temp_timestamp=records[-1].timestamp, records=records)


class FakePMClient:
    def __init__(self):
        self.market_calls = 0
        self.book_calls = 0
        self.mode = "paper"

    def fetch_market_tokens(self):
        self.market_calls += 1
        return {"16": "token-16"}

    def fetch_orderbooks(self, token_map):
        from src.polymarket.models import OutcomeBook

        self.book_calls += 1
        return {"16": OutcomeBook(outcome="16", token_id="token-16", best_bid=0.4, best_ask=0.6)}

    def implied_probabilities(self, books):
        return {"16": 1.0}

    def place_limit_order(self, req):
        return "paper-order"


class FakeSettings:
    date_iso = "2026-03-05"
    auto_rollover_target_date = True
    latitude = 49.0097
    longitude = 2.5479
    timezone = "Europe/Paris"
    weather_poll_seconds = 300
    market_poll_seconds = 60


class FakeWUClient:
    def __init__(self, value: int = 20):
        self.value = value
        self.calls = 0
        self.reset_calls = 0

    def fetch_daily_high_so_far(self):
        self.calls += 1
        return SimpleNamespace(high_so_far_c=self.value)

    def reset_cache(self):
        self.reset_calls += 1


def _session_for_polling(target_date: date, pm: FakePMClient | None = None) -> BotSession:
    pm_client = pm or FakePMClient()
    return BotSession(
        target_date=target_date,
        market_url=f"https://example.com/{target_date.isoformat()}",
        pm_client=pm_client,
        trader=Trader(FakeClientForTrader()),
        risk=SimpleNamespace(state=SimpleNamespace(order_timestamps=[])),
        runtime=RuntimeState(),
        polling=PollingState(),
    )


def test_polling_separates_weather_and_market_refresh(monkeypatch):
    settings = FakeSettings()
    weather = FakeWeatherClient()
    pm = FakePMClient()
    session = _session_for_polling(date(2026, 3, 5), pm)

    monkeypatch.setattr("src.main.evaluate_and_trade", lambda **kwargs: None)

    for current in [
        datetime(2026, 3, 5, 12, 0, tzinfo=TZ),
        datetime(2026, 3, 5, 12, 1, tzinfo=TZ),
        datetime(2026, 3, 5, 12, 2, tzinfo=TZ),
        datetime(2026, 3, 5, 12, 5, tzinfo=TZ),
    ]:
        run_scheduled_cycle(
            settings=settings,
            session=session,
            weather_client=weather,
            wu_client=None,
            log=object(),
            now_local=current,
        )

    assert weather.calls == 2
    assert pm.market_calls == 4
    assert pm.book_calls == 4


def test_cached_weather_reused_until_weather_poll_due(monkeypatch):
    settings = FakeSettings()
    weather = FakeWeatherClient()
    pm = FakePMClient()
    session = _session_for_polling(date(2026, 3, 5), pm)
    monkeypatch.setattr("src.main.evaluate_and_trade", lambda **kwargs: None)

    run_scheduled_cycle(
        settings=settings,
        session=session,
        weather_client=weather,
        wu_client=None,
        log=object(),
        now_local=datetime(2026, 3, 5, 12, 0, tzinfo=TZ),
    )
    first_weather = session.polling.weather

    run_scheduled_cycle(
        settings=settings,
        session=session,
        weather_client=weather,
        wu_client=None,
        log=object(),
        now_local=datetime(2026, 3, 5, 12, 1, tzinfo=TZ),
    )

    assert weather.calls == 1
    assert session.polling.weather is first_weather


class FakeClientForTrader:
    mode = "paper"

    def place_limit_order(self, req):
        return "paper-order"


class FakeNonPaperClientForTrader:
    mode = "live-sim"

    def place_limit_order(self, req):
        return "live-order"


def _lock19_inputs(main_target_usd: float) -> Lock19Inputs:
    records = [
        HourlyWeatherRecord(timestamp=datetime(2026, 3, 5, 17, 0, tzinfo=TZ), temperature_c=18.0, wind_kph=10, cloud_cover_pct=20),
        HourlyWeatherRecord(timestamp=datetime(2026, 3, 5, 18, 0, tzinfo=TZ), temperature_c=19.0, wind_kph=9, cloud_cover_pct=15),
    ]
    return Lock19Inputs(
        now_local=datetime(2026, 3, 5, 19, 5, tzinfo=TZ),
        target_date=date(2026, 3, 5),
        records=records,
        lock_time=time(19, 0),
        lock_window_start=time(13, 0),
        late_peak_risk=0.0,
        market_probs={"19": 0.3, ">=20": 0.2},
        model_probs={"19": 0.8, ">=20": 0.1},
        current_temp_c=19.0,
        edge_threshold=0.04,
        max_order_usd=25,
        main_target_usd=main_target_usd,
        hedge_enabled=False,
        hedge_risk_threshold=0.65,
        hedge_trend_hours=2,
        hedge_near_peak_delta_c=0.5,
        hedge_max_total_usd=20,
        hedge_only_if_edge_positive=False,
        main_only_if_edge_positive=False,
    )


def test_exposure_sync_uses_execution_state_not_loop_counter():
    trader = Trader(FakeClientForTrader())
    runtime = RuntimeState()

    runtime.lock19.main_exposure_usd = 999
    trader.execution.lock19_main_exposure_usd = 25
    trader.execution.lock19_hedge_exposure_usd = 5

    sync_lock19_exposure_from_execution(runtime, trader)

    assert runtime.lock19.main_exposure_usd == 25
    assert runtime.lock19.hedge_exposure_usd == 5


def test_repeated_cycles_do_not_overbuy_when_target_already_filled():
    trader = Trader(FakeClientForTrader())
    runtime = RuntimeState()

    trader.requote([LimitOrderRequest(token_id="t", outcome="19", price=0.5, size_usd=25)], lock19_main_bucket="19")
    runtime.lock19.main_bucket = "19"
    sync_lock19_exposure_from_execution(runtime, trader)

    plan = decide_lock19(runtime.lock19, _lock19_inputs(main_target_usd=25))
    assert not plan.should_place_main


def test_paper_immediate_fill_does_not_leave_open_order():
    trader = Trader(FakeClientForTrader())
    order = LimitOrderRequest(token_id="t", outcome="19", price=0.5, size_usd=10)

    trader.requote([order], lock19_main_bucket="19")

    assert trader.execution.lock19_main_exposure_usd == 10
    assert trader.get_open_order_ids() == []


def test_non_paper_requote_tracks_open_orders():
    trader = Trader(FakeNonPaperClientForTrader())
    order = LimitOrderRequest(token_id="t", outcome="19", price=0.5, size_usd=10)

    trader.requote([order], lock19_main_bucket="19")

    assert len(trader.get_open_order_ids()) == 1


def test_risk_reads_exposure_from_paper_execution_state():
    trader = Trader(FakeClientForTrader())
    risk = RiskManager(
        RiskLimits(max_total_exposure_usd=30, max_order_usd=30, max_orders_per_hour=10),
        exposure_provider=lambda: trader.execution.lock19_main_exposure_usd + trader.execution.lock19_hedge_exposure_usd,
    )
    order = LimitOrderRequest(token_id="t", outcome="19", price=0.5, size_usd=10)

    trader.requote([order], lock19_main_bucket="19")
    ok, reason = risk.validate_order(LimitOrderRequest(token_id="t", outcome="19", price=0.5, size_usd=25))

    assert not ok
    assert "total exposure" in reason


def test_legacy_mode_exposure_provider_reads_legacy_execution_state():
    trader = Trader(FakeClientForTrader())
    risk = RiskManager(
        RiskLimits(max_total_exposure_usd=30, max_order_usd=30, max_orders_per_hour=10),
        exposure_provider=lambda: trader.execution.exposure_for_mode("legacy"),
    )
    order = LimitOrderRequest(token_id="t", outcome="19", price=0.5, size_usd=20)

    trader.requote([order], strategy_mode="legacy")
    ok, reason = risk.validate_order(LimitOrderRequest(token_id="t", outcome="18", price=0.5, size_usd=15))

    assert not ok
    assert "total exposure" in reason


def test_resolve_active_target_date_auto_rollover_true():
    settings = FakeSettings()
    settings.auto_rollover_target_date = True
    settings.date_iso = "2026-03-03"

    resolved = resolve_active_target_date(settings, datetime(2026, 3, 6, 0, 5, tzinfo=TZ))

    assert resolved == date(2026, 3, 6)


def test_resolve_active_target_date_auto_rollover_false():
    settings = FakeSettings()
    settings.auto_rollover_target_date = False
    settings.date_iso = "2026-03-03"

    resolved = resolve_active_target_date(settings, datetime(2026, 3, 6, 0, 5, tzinfo=TZ))

    assert resolved == date(2026, 3, 3)


def test_day_rollover_rebuilds_market_and_resets_daily_state(monkeypatch):
    settings = FakeSettings()
    settings.auto_rollover_target_date = True

    class FakeLog:
        def __init__(self):
            self.messages = []

        def info(self, msg, *args):
            self.messages.append(msg % args)

    log = FakeLog()
    old_session = _session_for_polling(date(2026, 3, 5))
    old_session.trader.state.open_orders = {
        "paper-old": LimitOrderRequest(token_id="t", outcome="19", price=0.5, size_usd=10)
    }
    old_session.polling.weather = "stale"
    old_session.polling.market = "stale"
    old_session.risk.state.order_timestamps = [datetime(2026, 3, 5, 23, 40, tzinfo=TZ)]

    def _fake_build(settings_obj, target_date):
        trader = Trader(FakeClientForTrader())
        trader.execution.lock19_main_exposure_usd = 0.0
        session = BotSession(
            target_date=target_date,
            market_url=f"https://polymarket.com/event/highest-temperature-in-paris-on-march-{target_date.day}-2026",
            pm_client=FakePMClient(),
            trader=trader,
            risk=SimpleNamespace(state=SimpleNamespace(order_timestamps=[])),
            runtime=RuntimeState(),
            polling=PollingState(),
        )
        return session

    monkeypatch.setattr("src.main.build_bot_session", _fake_build)

    wu = FakeWUClient()
    new_session = maybe_rollover_session(settings, datetime(2026, 3, 6, 0, 1, tzinfo=TZ), old_session, log, wu)

    assert new_session.target_date == date(2026, 3, 6)
    assert new_session.market_url.endswith("march-6-2026")
    assert new_session.polling.weather is None
    assert new_session.polling.market is None
    assert new_session.risk.state.order_timestamps == [datetime(2026, 3, 5, 23, 40, tzinfo=TZ)]
    assert new_session is not old_session
    assert wu.reset_calls == 1
    assert any("target-date rollover" in message for message in log.messages)


def test_rollover_carries_order_timestamps_but_resets_daily_execution_state(monkeypatch):
    settings = FakeSettings()
    settings.auto_rollover_target_date = True
    old_trader = Trader(FakeClientForTrader())
    old_trader.execution.lock19_main_exposure_usd = 22.0
    old_session = BotSession(
        target_date=date(2026, 3, 5),
        market_url="https://example.com/old",
        pm_client=FakePMClient(),
        trader=old_trader,
        risk=SimpleNamespace(state=SimpleNamespace(order_timestamps=[datetime(2026, 3, 5, 23, 50, tzinfo=TZ)])),
        runtime=RuntimeState(),
        polling=PollingState(),
    )
    old_session.trader.state.open_orders = {
        "paper-old": LimitOrderRequest(token_id="t", outcome="19", price=0.5, size_usd=5)
    }

    def _fake_build(settings_obj, target_date):
        return BotSession(
            target_date=target_date,
            market_url="https://example.com/new",
            pm_client=FakePMClient(),
            trader=Trader(FakeClientForTrader()),
            risk=SimpleNamespace(state=SimpleNamespace(order_timestamps=[])),
            runtime=RuntimeState(),
            polling=PollingState(),
        )

    monkeypatch.setattr("src.main.build_bot_session", _fake_build)

    rolled = maybe_rollover_session(
        settings,
        datetime(2026, 3, 6, 0, 1, tzinfo=TZ),
        old_session,
        SimpleNamespace(info=lambda *args, **kwargs: None),
        FakeWUClient(),
    )

    assert rolled.risk.state.order_timestamps == [datetime(2026, 3, 5, 23, 50, tzinfo=TZ)]
    assert rolled.trader.execution.lock19_main_exposure_usd == 0.0


def test_paper_rollover_explicitly_clears_previous_open_orders(monkeypatch):
    settings = FakeSettings()
    settings.auto_rollover_target_date = True
    session = _session_for_polling(date(2026, 3, 5))
    session.trader.state.open_orders = {
        "paper-old-1": LimitOrderRequest(token_id="t1", outcome="19", price=0.5, size_usd=10),
        "paper-old-2": LimitOrderRequest(token_id="t2", outcome="18", price=0.4, size_usd=5),
    }

    monkeypatch.setattr("src.main.build_bot_session", lambda settings_obj, target_date: _session_for_polling(target_date))
    new_session = maybe_rollover_session(
        settings,
        datetime(2026, 3, 6, 0, 1, tzinfo=TZ),
        session,
        SimpleNamespace(info=lambda *args, **kwargs: None),
        FakeWUClient(),
    )

    assert session.trader.get_open_order_ids() == []
    assert new_session.trader.get_open_order_ids() == []


def test_live_rollover_does_not_silently_discard_open_orders(monkeypatch):
    class FakeLiveClient:
        mode = "live"

        def place_limit_order(self, req):
            return "live-order"

        def sync_or_cancel_open_orders_for_rollover(self, open_order_ids):
            raise RuntimeError("live rollover order sync not implemented")

    settings = FakeSettings()
    settings.auto_rollover_target_date = True
    old_session = BotSession(
        target_date=date(2026, 3, 5),
        market_url="https://example.com/old",
        pm_client=FakePMClient(),
        trader=Trader(FakeLiveClient()),
        risk=SimpleNamespace(state=SimpleNamespace(order_timestamps=[])),
        runtime=RuntimeState(),
        polling=PollingState(),
    )
    old_session.trader.state.open_orders = {
        "live-old": LimitOrderRequest(token_id="t", outcome="19", price=0.5, size_usd=10)
    }

    monkeypatch.setattr("src.main.build_bot_session", lambda settings_obj, target_date: _session_for_polling(target_date))

    with pytest.raises(RuntimeError, match="live rollover order sync"):
        maybe_rollover_session(
            settings,
            datetime(2026, 3, 6, 0, 1, tzinfo=TZ),
            old_session,
            SimpleNamespace(info=lambda *args, **kwargs: None),
            FakeWUClient(),
        )


def test_day_rollover_disabled_keeps_same_session():
    settings = FakeSettings()
    settings.auto_rollover_target_date = False
    settings.date_iso = "2026-03-05"
    session = _session_for_polling(date(2026, 3, 5))

    same = maybe_rollover_session(
        settings,
        datetime(2026, 3, 6, 0, 1, tzinfo=TZ),
        session,
        SimpleNamespace(info=lambda *args, **kwargs: None),
        FakeWUClient(),
    )

    assert same is session
    assert same.target_date == date(2026, 3, 5)


def test_wu_sanity_check_skipped_when_target_date_differs_from_local_date(monkeypatch):
    settings = FakeSettings()
    session = _session_for_polling(date(2026, 3, 4))
    weather = FakeWeatherClient()
    wu = FakeWUClient(value=99)
    messages: list[str] = []

    monkeypatch.setattr("src.main.evaluate_and_trade", lambda **kwargs: None)

    class _Log:
        def info(self, msg, *args):
            messages.append(msg % args)

    run_scheduled_cycle(
        settings=settings,
        session=session,
        weather_client=weather,
        wu_client=wu,
        log=_Log(),
        now_local=datetime(2026, 3, 5, 12, 0, tzinfo=TZ),
    )

    assert wu.calls == 0
    assert session.polling.wu_value is None
    assert any("skipping wunderground sanity-check" in message for message in messages)


def test_wu_sanity_check_runs_when_target_date_matches_local_date(monkeypatch):
    settings = FakeSettings()
    session = _session_for_polling(date(2026, 3, 5))
    weather = FakeWeatherClient()
    wu = FakeWUClient(value=17)

    monkeypatch.setattr("src.main.evaluate_and_trade", lambda **kwargs: None)

    run_scheduled_cycle(
        settings=settings,
        session=session,
        weather_client=weather,
        wu_client=wu,
        log=SimpleNamespace(info=lambda *args, **kwargs: None),
        now_local=datetime(2026, 3, 5, 12, 0, tzinfo=TZ),
    )

    assert wu.calls == 1
    assert session.polling.wu_value == 17


def test_execution_state_defined_once():
    import src.polymarket.trader as trader_module

    source = Path(trader_module.__file__).read_text(encoding="utf-8")
    assert source.count("class ExecutionState") == 1


def test_live_mode_raises_descriptive_not_implemented_error():
    from src.polymarket.clob_client import PolymarketClient

    client = PolymarketClient(market_id="abc", mode="live")
    with pytest.raises(RuntimeError, match="not implemented yet"):
        client.place_limit_order(LimitOrderRequest(token_id="t", outcome="19", price=0.5, size_usd=10))


def test_main_blocks_live_mode_with_friendly_message(monkeypatch):
    from src import main

    monkeypatch.setenv("MODE", "live")
    monkeypatch.setattr("sys.argv", ["prog"])
    with pytest.raises(RuntimeError, match="MODE=live is not fully implemented yet"):
        main.main()
