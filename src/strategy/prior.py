from __future__ import annotations

import logging
from datetime import date

from src.weather.open_meteo_client import OpenMeteoClient


def resolve_forecast_tmax(
    configured_forecast_tmax: float | None,
    target_date: date,
    latitude: float,
    longitude: float,
    timezone: str,
) -> float:
    log = logging.getLogger("polymeteo")

    if configured_forecast_tmax is not None:
        log.info("prior forecast source=manual FORECAST_TMAX_C=%.2f", configured_forecast_tmax)
        return configured_forecast_tmax

    client = OpenMeteoClient()
    try:
        api_tmax = client.get_daily_forecast_tmax(
            target_date=target_date, latitude=latitude, longitude=longitude, timezone=timezone
        )
        log.info("prior forecast source=open-meteo temperature_2m_max=%.2f", api_tmax)
        return api_tmax
    except Exception as exc:
        log.error("open-meteo forecast fetch failed: %s", exc)
        raise RuntimeError(
            "FORECAST_TMAX_C is not set and automatic Open-Meteo forecast fetch failed. "
            "Set FORECAST_TMAX_C or check network/API availability."
        ) from exc
