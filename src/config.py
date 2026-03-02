from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mode: Literal["paper", "live"] = Field(default="paper", alias="MODE")
    polymarket_private_key: str | None = Field(default=None, alias="POLYMARKET_PRIVATE_KEY")
    polymarket_api_key: str | None = Field(default=None, alias="POLYMARKET_API_KEY")
    market_url: str | None = Field(default=None, alias="MARKET_URL")
    market_id: str | None = Field(default=None, alias="MARKET_ID")

    max_total_exposure_usd: float = Field(default=250.0, alias="MAX_TOTAL_EXPOSURE_USD", gt=0)
    max_order_usd: float = Field(default=25.0, alias="MAX_ORDER_USD", gt=0)
    max_orders_per_hour: int = Field(default=20, alias="MAX_ORDERS_PER_HOUR", ge=1)
    max_slippage_bps: int = Field(default=50, alias="MAX_SLIPPAGE_BPS", ge=0)

    edge_threshold: float = Field(default=0.04, alias="EDGE_THRESHOLD", ge=0)
    forecast_tmax_c: float = Field(default=14.5, alias="FORECAST_TMAX_C")
    prior_sigma_c: float = Field(default=2.0, alias="PRIOR_SIGMA_C", gt=0)
    temperature_rounding: Literal["round", "floor"] = Field(default="round", alias="TEMPERATURE_ROUNDING")

    weather_poll_seconds: int = Field(default=300, alias="WEATHER_POLL_SECONDS", ge=30)
    market_poll_seconds: int = Field(default=60, alias="MARKET_POLL_SECONDS", ge=10)
    wu_poll_seconds: int = Field(default=3600, alias="WU_POLL_SECONDS", ge=300)
    timezone: str = Field(default="Europe/Paris", alias="TIMEZONE")

    latitude: float = Field(default=49.0097, alias="LFPG_LATITUDE")
    longitude: float = Field(default=2.5479, alias="LFPG_LONGITUDE")
    date_iso: str = Field(default="2026-03-03", alias="TARGET_DATE")

    kill_switch_env: int = Field(default=0, alias="KILL_SWITCH")
    kill_switch_path: str = Field(default="KILL", alias="KILL_SWITCH_PATH")

    dry_run_log_orders: bool = Field(default=True, alias="DRY_RUN_LOG_ORDERS")

    @model_validator(mode="after")
    def _validate_live_requirements(self) -> "Settings":
        if self.mode == "live":
            if not self.polymarket_private_key:
                raise ValueError("POLYMARKET_PRIVATE_KEY is required in live mode")
            if not self.market_id and not self.market_url:
                raise ValueError("MARKET_ID or MARKET_URL is required")
        return self

    @property
    def kill_switch_file(self) -> Path:
        return Path(self.kill_switch_path)


settings = Settings()
