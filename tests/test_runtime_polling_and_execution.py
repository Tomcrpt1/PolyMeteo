from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from src.main import PollingState, RuntimeState, run_scheduled_cycle, sync_lock19_exposure_from_execution
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
    latitude = 49.0097
    longitude = 2.5479
    timezone = "Europe/Paris"
    weather_poll_seconds = 300
    market_poll_seconds = 60


def test_polling_separates_weather_and_market_refresh(monkeypatch):
    settings = FakeSettings()
    weather = FakeWeatherClient()
    pm = FakePMClient()
    polling = PollingState()

    monkeypatch.setattr("src.main.evaluate_and_trade", lambda **kwargs: None)

    for current in [
        datetime(2026, 3, 5, 12, 0, tzinfo=TZ),
        datetime(2026, 3, 5, 12, 1, tzinfo=TZ),
        datetime(2026, 3, 5, 12, 2, tzinfo=TZ),
        datetime(2026, 3, 5, 12, 5, tzinfo=TZ),
    ]:
        run_scheduled_cycle(
            settings=settings,
            weather_client=weather,
            wu_client=None,
            pm_client=pm,
            trader=object(),
            risk=object(),
            log=object(),
            runtime=RuntimeState(),
            polling=polling,
            now_local=current,
        )

    assert weather.calls == 2
    assert pm.market_calls == 4
    assert pm.book_calls == 4


def test_cached_weather_reused_until_weather_poll_due(monkeypatch):
    settings = FakeSettings()
    weather = FakeWeatherClient()
    pm = FakePMClient()
    polling = PollingState()
    monkeypatch.setattr("src.main.evaluate_and_trade", lambda **kwargs: None)

    run_scheduled_cycle(
        settings=settings,
        weather_client=weather,
        wu_client=None,
        pm_client=pm,
        trader=object(),
        risk=object(),
        log=object(),
        runtime=RuntimeState(),
        polling=polling,
        now_local=datetime(2026, 3, 5, 12, 0, tzinfo=TZ),
    )
    first_weather = polling.weather

    run_scheduled_cycle(
        settings=settings,
        weather_client=weather,
        wu_client=None,
        pm_client=pm,
        trader=object(),
        risk=object(),
        log=object(),
        runtime=RuntimeState(),
        polling=polling,
        now_local=datetime(2026, 3, 5, 12, 1, tzinfo=TZ),
    )

    assert weather.calls == 1
    assert polling.weather is first_weather


class FakeClientForTrader:
    mode = "paper"

    def place_limit_order(self, req):
        return "paper-order"


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
