from datetime import date

import src.config as config_module
from src.config import Settings
from src.polymarket.market_resolution import (
    build_market_url_from_target_date,
    resolve_market_url,
    strip_url_fragment,
)


def test_build_market_url_from_target_date_exact_slug():
    built = build_market_url_from_target_date(
        target_date=date(2026, 3, 5),
        template="https://polymarket.com/event/highest-temperature-in-paris-on-{month_name}-{day}-{year}",
    )
    assert built == "https://polymarket.com/event/highest-temperature-in-paris-on-march-5-2026"


def test_build_market_url_day_is_not_zero_padded():
    built = build_market_url_from_target_date(
        target_date=date(2026, 3, 4),
        template="https://example.com/{month_name}-{day}-{year}",
    )
    assert built.endswith("march-4-2026")


def test_strip_url_fragment():
    assert (
        strip_url_fragment("https://polymarket.com/event/highest-temperature-in-paris-on-march-5-2026#abc")
        == "https://polymarket.com/event/highest-temperature-in-paris-on-march-5-2026"
    )


def test_resolve_market_url_uses_provided_market_url_instead_of_template(monkeypatch):
    monkeypatch.setenv("MARKET_ID", "")
    monkeypatch.setenv("MARKET_URL", "https://polymarket.com/event/custom-slug#ignored")
    monkeypatch.setenv("MARKET_URL_TEMPLATE", "https://example.com/{month_name}-{day}-{year}")

    settings = Settings()
    resolved = resolve_market_url(settings, date(2026, 3, 5))

    assert resolved == "https://polymarket.com/event/custom-slug"


def test_market_url_empty_string_is_none(monkeypatch):
    monkeypatch.setenv("MARKET_URL", "")
    settings = Settings()
    assert settings.market_url is None


def test_default_market_url_template_builds_expected_paris_slug():
    settings = Settings()
    built = build_market_url_from_target_date(date(2026, 3, 5), settings.market_url_template)
    assert built == "https://polymarket.com/event/highest-temperature-in-paris-on-march-5-2026"


def test_config_module_has_no_global_settings_singleton():
    assert not hasattr(config_module, "settings")
