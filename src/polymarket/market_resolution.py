from __future__ import annotations

from datetime import date
from urllib.parse import urlparse, urlunparse

from src.config import Settings


def strip_url_fragment(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, ""))


def build_market_url_from_target_date(target_date: date, template: str, city_slug: str = "paris") -> str:
    return template.format(
        month_name=target_date.strftime("%B").lower(),
        day=target_date.day,
        year=target_date.year,
        city_slug=city_slug,
    )


def resolve_market_url(settings: Settings, target_date: date) -> str | None:
    if settings.market_id:
        return None
    if settings.market_url:
        return strip_url_fragment(settings.market_url)
    return build_market_url_from_target_date(target_date, settings.market_url_template, settings.market_city_slug)
