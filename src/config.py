from __future__ import annotations

from pathlib import Path
from datetime import time
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mode: Literal["paper", "live"] = Field(default="paper", alias="MODE")
    polymarket_private_key: str | None = Field(default=None, alias="POLYMARKET_PRIVATE_KEY")
    polymarket_api_key: str | None = Field(default=None, alias="POLYMARKET_API_KEY")
    market_url: str | None = Field(default=None, alias="MARKET_URL")
    market_id: str | None = Field(default=None, alias="MARKET_ID")
    market_url_template: str = Field(
        default="https://polymarket.com/event/highest-temperature-in-paris-on-{month_name}-{day}-{year}",
        alias="MARKET_URL_TEMPLATE",
    )
    market_city_slug: str = Field(default="paris", alias="MARKET_CITY_SLUG")

    max_total_exposure_usd: float = Field(default=250.0, alias="MAX_TOTAL_EXPOSURE_USD", gt=0)
    max_order_usd: float = Field(default=25.0, alias="MAX_ORDER_USD", gt=0)
    max_orders_per_hour: int = Field(default=20, alias="MAX_ORDERS_PER_HOUR", ge=1)
    max_slippage_bps: int = Field(default=50, alias="MAX_SLIPPAGE_BPS", ge=0)

    edge_threshold: float = Field(default=0.04, alias="EDGE_THRESHOLD", ge=0)
    strategy_mode: Literal["lock19", "legacy"] = Field(default="lock19", alias="STRATEGY_MODE")
    lock_time_local: str = Field(default="19:00", alias="LOCK_TIME_LOCAL")
    lock_window_start_local: str = Field(default="00:00", alias="LOCK_WINDOW_START_LOCAL")
    hedge_enabled: bool = Field(default=True, alias="HEDGE_ENABLED")
    hedge_risk_threshold: float = Field(default=0.65, alias="HEDGE_RISK_THRESHOLD", ge=0, le=1)
    hedge_trend_hours: int = Field(default=2, alias="HEDGE_TREND_HOURS", ge=1)
    hedge_near_peak_delta_c: float = Field(default=0.5, alias="HEDGE_NEAR_PEAK_DELTA_C", ge=0)
    hedge_max_total_usd: float | None = Field(default=None, alias="HEDGE_MAX_TOTAL_USD", gt=0)
    hedge_only_if_edge_positive: bool = Field(default=True, alias="HEDGE_ONLY_IF_EDGE_POSITIVE")
    main_only_if_edge_positive: bool = Field(default=True, alias="MAIN_ONLY_IF_EDGE_POSITIVE")
    forecast_tmax_c: float | None = Field(default=None, alias="FORECAST_TMAX_C")
    prior_sigma_c: float = Field(default=2.0, alias="PRIOR_SIGMA_C", gt=0)
    temperature_rounding: Literal["round", "floor"] = Field(default="round", alias="TEMPERATURE_ROUNDING")

    weather_poll_seconds: int = Field(default=300, alias="WEATHER_POLL_SECONDS", ge=30)
    market_poll_seconds: int = Field(default=60, alias="MARKET_POLL_SECONDS", ge=10)
    wu_poll_seconds: int = Field(default=3600, alias="WU_POLL_SECONDS", ge=300)
    timezone: str = Field(default="Europe/Paris", alias="TIMEZONE")

    latitude: float = Field(default=49.0097, alias="LFPG_LATITUDE")
    longitude: float = Field(default=2.5479, alias="LFPG_LONGITUDE")
    date_iso: str = Field(default="2026-03-03", alias="TARGET_DATE")
    auto_rollover_target_date: bool = Field(default=True, alias="AUTO_ROLLOVER_TARGET_DATE")

    kill_switch_env: int = Field(default=0, alias="KILL_SWITCH")
    kill_switch_path: str = Field(default="KILL", alias="KILL_SWITCH_PATH")

    dry_run_log_orders: bool = Field(default=True, alias="DRY_RUN_LOG_ORDERS")


    @field_validator("forecast_tmax_c", mode="before")
    @classmethod
    def _empty_forecast_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("market_url", mode="before")
    @classmethod
    def _empty_market_url_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @staticmethod
    def _parse_hhmm(value: str) -> time:
        hour_s, minute_s = value.split(":", maxsplit=1)
        return time(hour=int(hour_s), minute=int(minute_s))

    @property
    def lock_time(self) -> time:
        return self._parse_hhmm(self.lock_time_local)

    @property
    def lock_window_start(self) -> time:
        return self._parse_hhmm(self.lock_window_start_local)

    @property
    def hedge_max_total_usd_effective(self) -> float:
        if self.hedge_max_total_usd is not None:
            return self.hedge_max_total_usd
        return self.max_total_exposure_usd * 0.2

    @property
    def kill_switch_file(self) -> Path:
        return Path(self.kill_switch_path)
