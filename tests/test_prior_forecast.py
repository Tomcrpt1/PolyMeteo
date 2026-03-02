from datetime import date

import pytest

from src.config import Settings
from src.strategy.prior import resolve_forecast_tmax


def test_forecast_env_empty_string_is_none(monkeypatch):
    monkeypatch.setenv("FORECAST_TMAX_C", "")
    cfg = Settings()
    assert cfg.forecast_tmax_c is None


def test_resolve_forecast_uses_manual_value():
    value = resolve_forecast_tmax(
        configured_forecast_tmax=13.5,
        target_date=date(2026, 3, 3),
        latitude=49.0097,
        longitude=2.5479,
        timezone="Europe/Paris",
    )
    assert value == 13.5


def test_resolve_forecast_uses_api_when_manual_missing(monkeypatch):
    monkeypatch.setattr(
        "src.weather.open_meteo_client.OpenMeteoClient.get_daily_forecast_tmax",
        lambda self, target_date, latitude, longitude, timezone: 15.2,
    )
    value = resolve_forecast_tmax(
        configured_forecast_tmax=None,
        target_date=date(2026, 3, 3),
        latitude=49.0097,
        longitude=2.5479,
        timezone="Europe/Paris",
    )
    assert value == 15.2


def test_resolve_forecast_raises_if_api_fails_and_no_manual(monkeypatch):
    def _boom(self, target_date, latitude, longitude, timezone):
        raise RuntimeError("api down")

    monkeypatch.setattr("src.weather.open_meteo_client.OpenMeteoClient.get_daily_forecast_tmax", _boom)

    with pytest.raises(RuntimeError, match="FORECAST_TMAX_C is not set"):
        resolve_forecast_tmax(
            configured_forecast_tmax=None,
            target_date=date(2026, 3, 3),
            latitude=49.0097,
            longitude=2.5479,
            timezone="Europe/Paris",
        )
