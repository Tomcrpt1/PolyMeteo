from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

from src.utils.retry import network_retry
from src.weather.models import TemperatureSample, WeatherSnapshot


@dataclass(slots=True)
class MeteoConditions:
    snapshot: WeatherSnapshot
    recent_samples: list[TemperatureSample]
    recent_wind_kph: list[float]
    recent_cloud_pct: list[float]


class MeteostatClient:
    """API-friendly weather client using Open-Meteo endpoints for LFPG coordinates."""

    def __init__(self, latitude: float, longitude: float, timezone: str, timeout_s: int = 15):
        self.latitude = latitude
        self.longitude = longitude
        self.timezone = timezone
        self.client = httpx.Client(timeout=timeout_s)

    @network_retry
    def fetch_conditions(self, target_date: date) -> MeteoConditions:
        date_str = target_date.isoformat()
        endpoint = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "hourly": "temperature_2m,wind_speed_10m,cloud_cover",
            "timezone": self.timezone,
            "start_date": date_str,
            "end_date": date_str,
            "forecast_days": 1,
        }
        response = self.client.get(endpoint, params=params)
        response.raise_for_status()
        payload = response.json()

        hours = payload.get("hourly", {}).get("time", [])
        temps = payload.get("hourly", {}).get("temperature_2m", [])
        winds = payload.get("hourly", {}).get("wind_speed_10m", [])
        clouds = payload.get("hourly", {}).get("cloud_cover", [])

        tz = ZoneInfo(self.timezone)
        now = datetime.now(tz)
        samples: list[TemperatureSample] = []
        wind_recent: list[float] = []
        cloud_recent: list[float] = []

        for t, temp, wind, cloud in zip(hours, temps, winds, clouds):
            ts = datetime.fromisoformat(t).replace(tzinfo=tz)
            if ts <= now:
                samples.append(TemperatureSample(timestamp=ts, temperature_c=float(temp)))
                wind_recent.append(float(wind))
                cloud_recent.append(float(cloud))

        if not samples:
            raise RuntimeError("No weather samples available for target day yet")

        max_sample = max(samples, key=lambda s: s.temperature_c)
        current = samples[-1]
        snapshot = WeatherSnapshot(
            fetched_at=now,
            current_temp_c=current.temperature_c,
            max_temp_so_far_c=max_sample.temperature_c,
            max_temp_timestamp=max_sample.timestamp,
            source="open-meteo",
        )
        return MeteoConditions(snapshot=snapshot, recent_samples=samples[-6:], recent_wind_kph=wind_recent[-6:], recent_cloud_pct=cloud_recent[-6:])
