from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.weather.models import TemperatureSample, WeatherSnapshot
from src.weather.open_meteo_client import OpenMeteoClient


@dataclass(slots=True)
class MeteoConditions:
    snapshot: WeatherSnapshot
    recent_samples: list[TemperatureSample]
    recent_wind_kph: list[float]
    recent_cloud_pct: list[float]


class MeteostatClient:
    """Backward-compatible wrapper around Open-Meteo hourly conditions."""

    def __init__(self, latitude: float, longitude: float, timezone: str, timeout_s: int = 15):
        self.latitude = latitude
        self.longitude = longitude
        self.timezone = timezone
        self.client = OpenMeteoClient(timeout_s=timeout_s)

    def fetch_conditions(self, target_date: date) -> MeteoConditions:
        conditions = self.client.fetch_hourly_conditions(target_date, self.latitude, self.longitude, self.timezone)
        samples = [TemperatureSample(timestamp=r.timestamp, temperature_c=r.temperature_c) for r in conditions.records[-6:]]
        snapshot = WeatherSnapshot(
            fetched_at=conditions.last_updated,
            current_temp_c=conditions.current_temp_c,
            max_temp_so_far_c=conditions.max_temp_so_far_c,
            max_temp_timestamp=conditions.max_temp_timestamp,
            source="open-meteo",
        )
        return MeteoConditions(
            snapshot=snapshot,
            recent_samples=samples,
            recent_wind_kph=[r.wind_kph for r in conditions.records[-6:]],
            recent_cloud_pct=[r.cloud_cover_pct for r in conditions.records[-6:]],
        )
