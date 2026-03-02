from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from src.polymarket.markets import BUCKETS, map_temp_to_bucket
from src.weather.models import HourlyWeatherRecord


@dataclass(slots=True)
class Lock19State:
    main_bucket: str | None = None
    main_exposure_usd: float = 0.0
    hedge_exposure_usd: float = 0.0


@dataclass(slots=True)
class Lock19Inputs:
    now_local: datetime
    target_date: date
    records: list[HourlyWeatherRecord]
    lock_time: time
    lock_window_start: time
    late_peak_risk: float
    market_probs: dict[str, float]
    model_probs: dict[str, float]
    current_temp_c: float
    edge_threshold: float
    max_order_usd: float
    main_target_usd: float
    hedge_enabled: bool
    hedge_risk_threshold: float
    hedge_trend_hours: int
    hedge_near_peak_delta_c: float
    hedge_max_total_usd: float
    hedge_only_if_edge_positive: bool
    main_only_if_edge_positive: bool
    temperature_rounding: str = "round"


@dataclass(slots=True)
class Lock19Plan:
    main_bucket: str | None
    locked_max_c: float | None
    locked_max_int: int | None
    should_place_main: bool = False
    should_place_hedge: bool = False
    hedge_bucket: str | None = None
    main_order_usd: float = 0.0
    hedge_order_usd: float = 0.0
    reason: str = ""


def get_max_between(records: list[HourlyWeatherRecord], target_date: date, start_local_time: time, end_local_time: time) -> float | None:
    values = [
        r.temperature_c
        for r in records
        if r.timestamp.date() == target_date and start_local_time <= r.timestamp.time() <= end_local_time
    ]
    if not values:
        return None
    return max(values)


def next_higher_bucket(bucket: str) -> str | None:
    idx = BUCKETS.index(bucket)
    if idx >= len(BUCKETS) - 1:
        return None
    return BUCKETS[idx + 1]


def rising_trend(records: list[HourlyWeatherRecord], hours: int) -> bool:
    if len(records) < hours + 1:
        return False
    subset = records[-(hours + 1) :]
    return subset[-1].temperature_c > subset[0].temperature_c


def decide_lock19(state: Lock19State, inputs: Lock19Inputs) -> Lock19Plan:
    if inputs.now_local.time() < inputs.lock_time:
        return Lock19Plan(main_bucket=state.main_bucket, locked_max_c=None, locked_max_int=None, reason="before lock time")

    locked_max_c = get_max_between(inputs.records, inputs.target_date, inputs.lock_window_start, inputs.lock_time)
    if locked_max_c is None:
        return Lock19Plan(main_bucket=None, locked_max_c=None, locked_max_int=None, reason="no records in lock window")

    locked_max_int = int(round(locked_max_c)) if inputs.temperature_rounding == "round" else int(locked_max_c)
    main_bucket = map_temp_to_bucket(locked_max_int)

    market_main = inputs.market_probs.get(main_bucket, 0.0)
    model_main = inputs.model_probs.get(main_bucket, 0.0) if inputs.main_only_if_edge_positive else 1.0
    main_edge = model_main - market_main

    plan = Lock19Plan(main_bucket=main_bucket, locked_max_c=locked_max_c, locked_max_int=locked_max_int)

    if state.main_bucket is None:
        state.main_bucket = main_bucket

    if state.main_bucket == main_bucket and state.main_exposure_usd + 0.01 < inputs.main_target_usd:
        if (not inputs.main_only_if_edge_positive) or (main_edge > inputs.edge_threshold):
            plan.should_place_main = True
            remaining = inputs.main_target_usd - state.main_exposure_usd
            plan.main_order_usd = min(inputs.max_order_usd, remaining)
        else:
            plan.reason = f"main edge below threshold ({main_edge:.3f})"

    if not inputs.hedge_enabled:
        return plan

    hedge_bucket = next_higher_bucket(main_bucket)
    if hedge_bucket is None:
        return plan

    near_peak = inputs.current_temp_c >= (locked_max_c - inputs.hedge_near_peak_delta_c)
    trend_up = rising_trend(inputs.records, inputs.hedge_trend_hours)
    hedge_signal = inputs.late_peak_risk >= inputs.hedge_risk_threshold or (near_peak and trend_up)
    if not hedge_signal:
        return plan

    hedge_edge = inputs.model_probs.get(hedge_bucket, 0.0) - inputs.market_probs.get(hedge_bucket, 0.0)
    if inputs.hedge_only_if_edge_positive and hedge_edge <= inputs.edge_threshold:
        plan.reason = f"hedge edge below threshold ({hedge_edge:.3f})"
        return plan

    remaining_budget = inputs.hedge_max_total_usd - state.hedge_exposure_usd
    if remaining_budget <= 0:
        plan.reason = "hedge budget exhausted"
        return plan

    plan.should_place_hedge = True
    plan.hedge_bucket = hedge_bucket
    plan.hedge_order_usd = min(inputs.max_order_usd, remaining_budget)
    return plan
