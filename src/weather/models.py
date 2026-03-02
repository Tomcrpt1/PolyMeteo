from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TemperatureSample(BaseModel):
    timestamp: datetime
    temperature_c: float


class WeatherSnapshot(BaseModel):
    fetched_at: datetime
    current_temp_c: float
    max_temp_so_far_c: float
    max_temp_timestamp: datetime | None
    station: str = "LFPG"
    source: str


class HourlyWeatherRecord(BaseModel):
    timestamp: datetime
    temperature_c: float
    wind_kph: float
    cloud_cover_pct: float


class WeatherConditions(BaseModel):
    last_updated: datetime
    current_temp_c: float
    max_temp_so_far_c: float
    max_temp_timestamp: datetime | None
    records: list[HourlyWeatherRecord]
