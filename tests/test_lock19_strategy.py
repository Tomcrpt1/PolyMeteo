from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from src.strategy.lock19 import Lock19Inputs, Lock19State, decide_lock19, get_max_between
from src.weather.models import HourlyWeatherRecord


TZ = ZoneInfo("Europe/Paris")


def _record(hour: int, temp: float) -> HourlyWeatherRecord:
    return HourlyWeatherRecord(timestamp=datetime(2026, 3, 3, hour, 0, tzinfo=TZ), temperature_c=temp, wind_kph=8, cloud_cover_pct=20)


def _inputs(now_hour: int, records: list[HourlyWeatherRecord]) -> Lock19Inputs:
    return Lock19Inputs(
        now_local=datetime(2026, 3, 3, now_hour, 5, tzinfo=TZ),
        target_date=date(2026, 3, 3),
        records=records,
        lock_time=time(19, 0),
        lock_window_start=time(0, 0),
        late_peak_risk=0.2,
        market_probs={"<=12": 0.01, "13": 0.03, "14": 0.05, "15": 0.08, "16": 0.2, "17": 0.2, "18": 0.18, "19": 0.12, ">=20": 0.13},
        model_probs={"<=12": 0.01, "13": 0.02, "14": 0.03, "15": 0.05, "16": 0.14, "17": 0.15, "18": 0.2, "19": 0.23, ">=20": 0.17},
        current_temp_c=18.5,
        edge_threshold=0.04,
        max_order_usd=25,
        main_target_usd=100,
        hedge_enabled=True,
        hedge_risk_threshold=0.65,
        hedge_trend_hours=2,
        hedge_near_peak_delta_c=0.5,
        hedge_max_total_usd=20,
        hedge_only_if_edge_positive=False,
        main_only_if_edge_positive=False,
    )


def test_before_lock_time_no_main_order():
    state = Lock19State()
    records = [_record(16, 18.2), _record(17, 18.9), _record(18, 19.2)]
    plan = decide_lock19(state, _inputs(18, records))
    assert not plan.should_place_main
    assert plan.reason == "before lock time"


def test_after_lock_places_exactly_one_main_bucket():
    state = Lock19State()
    records = [_record(15, 18.1), _record(17, 19.2), _record(18, 19.4)]
    plan = decide_lock19(state, _inputs(19, records))
    assert plan.should_place_main
    assert plan.main_bucket == "19"
    assert plan.hedge_bucket is None


def test_hedge_triggers_by_risk_or_near_peak_rising():
    records = [_record(17, 18.3), _record(18, 18.8), _record(19, 19.0)]

    by_risk = _inputs(20, records)
    by_risk.late_peak_risk = 0.8
    state1 = Lock19State(main_bucket="19")
    plan1 = decide_lock19(state1, by_risk)
    assert plan1.should_place_hedge
    assert plan1.hedge_bucket == ">=20"

    by_trend = _inputs(20, records)
    by_trend.late_peak_risk = 0.2
    by_trend.current_temp_c = 19.0
    state2 = Lock19State(main_bucket="19")
    plan2 = decide_lock19(state2, by_trend)
    assert plan2.should_place_hedge
    assert plan2.hedge_bucket == ">=20"


def test_hedge_capped_by_total_budget_and_next_bucket_only():
    state = Lock19State(main_bucket="18", hedge_exposure_usd=18)
    records = [_record(16, 17.2), _record(17, 17.9), _record(18, 18.2), _record(19, 18.4)]
    inputs = _inputs(20, records)
    inputs.late_peak_risk = 0.9
    plan = decide_lock19(state, inputs)
    assert plan.should_place_hedge
    assert plan.hedge_bucket == "19"
    assert plan.hedge_order_usd == 2


def test_lock_window_max_for_midnight_and_afternoon_start():
    records = [_record(10, 14.0), _record(14, 17.5), _record(16, 18.2), _record(18, 17.8)]
    full_day = get_max_between(records, date(2026, 3, 3), time(0, 0), time(19, 0))
    afternoon = get_max_between(records, date(2026, 3, 3), time(14, 0), time(19, 0))
    assert full_day == 18.2
    assert afternoon == 18.2
