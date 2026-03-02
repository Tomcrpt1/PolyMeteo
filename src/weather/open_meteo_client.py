from __future__ import annotations

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.weather.models import HourlyWeatherRecord, WeatherConditions


class OpenMeteoClient:
    """Open-Meteo client with a single query strategy (start_date/end_date windows only)."""

    def __init__(self, timeout_s: int = 15):
        self.client = httpx.Client(timeout=timeout_s)
        self.log = logging.getLogger("polymeteo")

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, httpx.TimeoutException):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code >= 500
        return False

    @retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=4), retry=retry_if_exception(_is_retryable.__func__))
    def _get(self, endpoint: str, params: dict[str, str | float]) -> dict:
        response = self.client.get(endpoint, params=params)
        if response.status_code == 400:
            self.log.error("Open-Meteo 400 url=%s body=%s", response.request.url, response.text)
        response.raise_for_status()
        return response.json()

    def fetch_hourly_conditions(self, target_date: date, latitude: float, longitude: float, timezone: str) -> WeatherConditions:
        date_str = target_date.isoformat()
        payload = self._get(
            "https://api.open-meteo.com/v1/forecast",
            {
                "latitude": latitude,
                "longitude": longitude,
                "hourly": "temperature_2m,wind_speed_10m,cloud_cover",
                "timezone": timezone,
                "start_date": date_str,
                "end_date": date_str,
            },
        )

        hourly = payload.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        winds = hourly.get("wind_speed_10m", [])
        clouds = hourly.get("cloud_cover", [])

        tz = ZoneInfo(timezone)
        now = datetime.now(tz)
        records: list[HourlyWeatherRecord] = []
        for t, temp, wind, cloud in zip(times, temps, winds, clouds):
            ts = datetime.fromisoformat(t).replace(tzinfo=tz)
            if ts <= now:
                records.append(
                    HourlyWeatherRecord(
                        timestamp=ts,
                        temperature_c=float(temp),
                        wind_kph=float(wind),
                        cloud_cover_pct=float(cloud),
                    )
                )

        if not records:
            raise RuntimeError("No hourly Open-Meteo records available up to current time")

        current = records[-1]
        max_record = max(records, key=lambda r: r.temperature_c)
        return WeatherConditions(
            last_updated=now,
            current_temp_c=current.temperature_c,
            max_temp_so_far_c=max_record.temperature_c,
            max_temp_timestamp=max_record.timestamp,
            records=records,
        )

    def get_daily_forecast_tmax(self, target_date: date, latitude: float, longitude: float, timezone: str) -> float:
        date_str = target_date.isoformat()
        payload = self._get(
            "https://api.open-meteo.com/v1/forecast",
            {
                "latitude": latitude,
                "longitude": longitude,
                "daily": "temperature_2m_max",
                "timezone": timezone,
                "start_date": date_str,
                "end_date": date_str,
            },
        )

        daily = payload.get("daily", {})
        days = daily.get("time", [])
        tmaxes = daily.get("temperature_2m_max", [])
        for day, tmax in zip(days, tmaxes):
            if day == date_str and tmax is not None:
                return float(tmax)
        raise RuntimeError(f"No daily temperature_2m_max returned for {date_str}")
