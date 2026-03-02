from __future__ import annotations

from datetime import datetime

from src.weather.models import TemperatureSample


def compute_late_peak_risk(
    recent_samples: list[TemperatureSample],
    max_temp_timestamp: datetime | None,
    now_local: datetime,
    recent_wind_kph: list[float] | None = None,
    recent_cloud_pct: list[float] | None = None,
) -> tuple[float, list[str]]:
    if len(recent_samples) < 2:
        return 0.1, ["insufficient samples"]

    reasons: list[str] = []
    trend = recent_samples[-1].temperature_c - recent_samples[0].temperature_c
    trend_score = max(0.0, min(1.0, (trend + 1) / 4))
    if trend > 0.4:
        reasons.append(f"positive trend {trend:.1f}C")

    recency_score = 0.0
    if max_temp_timestamp:
        minutes_since_max = (now_local - max_temp_timestamp).total_seconds() / 60
        recency_score = max(0.0, min(1.0, (120 - minutes_since_max) / 120))
        if minutes_since_max <= 120:
            reasons.append("recent max observed")

    hour = now_local.hour
    diurnal = 0.7 if hour <= 18 else max(0.05, 0.7 - 0.1 * (hour - 18))
    if hour > 18 and trend > 0.5:
        diurnal += 0.2
        reasons.append("evening warming")

    wind_bonus = 0.0
    if recent_wind_kph:
        avg_wind = sum(recent_wind_kph) / len(recent_wind_kph)
        wind_bonus = min(0.1, avg_wind / 200)
    cloud_penalty = 0.0
    if recent_cloud_pct:
        avg_cloud = sum(recent_cloud_pct) / len(recent_cloud_pct)
        cloud_penalty = min(0.1, avg_cloud / 1000)

    score = 0.45 * trend_score + 0.25 * recency_score + 0.3 * diurnal + wind_bonus - cloud_penalty
    score = max(0.0, min(1.0, score))
    if not reasons:
        reasons.append("normal diurnal decay")
    return score, reasons
