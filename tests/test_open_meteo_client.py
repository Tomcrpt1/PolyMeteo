from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

from src.weather.open_meteo_client import OpenMeteoClient


def test_hourly_request_does_not_mix_forecast_days_and_start_end(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        payload = {
            "hourly": {
                "time": ["2026-03-03T00:00", "2026-03-03T01:00"],
                "temperature_2m": [10.0, 11.0],
                "wind_speed_10m": [8.0, 9.0],
                "cloud_cover": [20.0, 30.0],
            }
        }
        return httpx.Response(200, json=payload, request=request)

    client = OpenMeteoClient()
    client.client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr("src.weather.open_meteo_client.datetime", _fixed_datetime(2026, 3, 3, 1, 30))

    client.fetch_hourly_conditions(date(2026, 3, 3), 49.0097, 2.5479, "Europe/Paris")

    assert "start_date=2026-03-03" in captured["url"]
    assert "end_date=2026-03-03" in captured["url"]
    assert "forecast_days" not in captured["url"]


def test_daily_tmax_parsing():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {"daily": {"time": ["2026-03-03"], "temperature_2m_max": [16.4]}}
        return httpx.Response(200, json=payload, request=request)

    client = OpenMeteoClient()
    client.client = httpx.Client(transport=httpx.MockTransport(handler))
    tmax = client.get_daily_forecast_tmax(date(2026, 3, 3), 49.0097, 2.5479, "Europe/Paris")
    assert tmax == 16.4


def test_hourly_parsing_max_so_far(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {
            "hourly": {
                "time": ["2026-03-03T00:00", "2026-03-03T01:00", "2026-03-03T02:00"],
                "temperature_2m": [9.0, 12.0, 11.0],
                "wind_speed_10m": [5.0, 6.0, 7.0],
                "cloud_cover": [10.0, 15.0, 20.0],
            }
        }
        return httpx.Response(200, json=payload, request=request)

    client = OpenMeteoClient()
    client.client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr("src.weather.open_meteo_client.datetime", _fixed_datetime(2026, 3, 3, 2, 30))

    conditions = client.fetch_hourly_conditions(date(2026, 3, 3), 49.0097, 2.5479, "Europe/Paris")
    assert conditions.current_temp_c == 11.0
    assert conditions.max_temp_so_far_c == 12.0
    assert conditions.max_temp_timestamp.hour == 1


def _fixed_datetime(y: int, m: int, d: int, hh: int, mm: int):
    class _DT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(y, m, d, hh, mm, tzinfo=tz or ZoneInfo("Europe/Paris"))

    return _DT
