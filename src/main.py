from __future__ import annotations

import argparse
import logging
import time

from src.config import Settings
from src.logger import setup_logger
from src.polymarket.clob_client import PolymarketClient
from src.polymarket.markets import BUCKETS
from src.polymarket.trader import Trader
from src.risk.kill_switch import kill_switch_active
from src.risk.limits import RiskLimits, RiskManager
from src.strategy.decision import DecisionConfig, decide_orders
from src.strategy.late_peak_risk import compute_late_peak_risk
from src.strategy.nowcast import update_intraday_distribution
from src.strategy.prior import resolve_forecast_tmax
from src.strategy.priors import gaussian_prior
from src.utils.time import now_tz, parse_date
from src.weather.models import TemperatureSample
from src.weather.open_meteo_client import OpenMeteoClient
from src.weather.wunderground_client import WundergroundClient


def run_cycle(
    settings: Settings,
    weather_client: OpenMeteoClient,
    wu_client: WundergroundClient | None,
    pm_client: PolymarketClient,
    trader: Trader,
    risk: RiskManager,
    log: logging.Logger,
) -> None:
    if kill_switch_active(settings.kill_switch_env, settings.kill_switch_file):
        log.warning("Kill switch active; monitoring only")
        return

    target_date = parse_date(settings.date_iso)
    conditions = weather_client.fetch_hourly_conditions(target_date, settings.latitude, settings.longitude, settings.timezone)
    rounded_max = int(round(conditions.max_temp_so_far_c)) if settings.temperature_rounding == "round" else int(conditions.max_temp_so_far_c)

    wu_value = None
    if wu_client:
        wu = wu_client.fetch_daily_high_so_far()
        wu_value = wu.high_so_far_c

    now_local = now_tz(settings.timezone)
    resolved_forecast_tmax = resolve_forecast_tmax(
        configured_forecast_tmax=settings.forecast_tmax_c,
        target_date=target_date,
        latitude=settings.latitude,
        longitude=settings.longitude,
        timezone=settings.timezone,
    )
    prior = gaussian_prior(resolved_forecast_tmax, settings.prior_sigma_c)
    late_risk, reasons = compute_late_peak_risk(
        recent_samples=[TemperatureSample(timestamp=r.timestamp, temperature_c=r.temperature_c) for r in conditions.records[-6:]],
        max_temp_timestamp=conditions.max_temp_timestamp,
        now_local=now_local,
        recent_wind_kph=[r.wind_kph for r in conditions.records[-6:]],
        recent_cloud_pct=[r.cloud_cover_pct for r in conditions.records[-6:]],
    )
    posterior = update_intraday_distribution(prior, rounded_max, now_local, late_risk)

    log.info(
        "weather source=%s current=%.1fC max_so_far=%.1fC rounded=%d wu=%s late_risk=%.2f reasons=%s",
        "open-meteo",
        conditions.current_temp_c,
        conditions.max_temp_so_far_c,
        rounded_max,
        wu_value,
        late_risk,
        ",".join(reasons),
    )
    top = sorted(posterior.items(), key=lambda x: x[1], reverse=True)[:3]
    log.info("model top buckets: %s", top)

    token_map = pm_client.fetch_market_tokens()
    books = pm_client.fetch_orderbooks(token_map)
    implied = pm_client.implied_probabilities(books)
    log.info("market implied: %s", {b: round(implied.get(b, 0), 3) for b in BUCKETS})

    decision = decide_orders(
        model_probs=posterior,
        market_books=books,
        token_map=token_map,
        late_peak_risk=late_risk,
        cfg=DecisionConfig(edge_threshold=settings.edge_threshold, max_order_usd=settings.max_order_usd),
    )
    if not decision.should_trade:
        log.info("no trade: %s", decision.reason)
        return

    approved = []
    for order in decision.orders:
        ok, reason = risk.validate_order(order)
        if ok:
            approved.append(order)
        else:
            log.warning("risk blocked order %s: %s", order.outcome, reason)

    if not approved:
        log.info("all orders blocked by risk")
        return

    ids = trader.requote(approved)
    for order in approved:
        risk.register_order(order)
    log.info("placed %d orders ids=%s", len(ids), ids)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Polymarket weather bot")
    parser.add_argument("--mode", choices=["paper", "live"], default=None)
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    settings = Settings()
    if args.mode:
        settings.mode = args.mode

    log = setup_logger()
    weather = OpenMeteoClient()
    wu = WundergroundClient("https://www.wunderground.com/history/daily/fr/paris/LFPG", settings.wu_poll_seconds)
    pm = PolymarketClient(settings.market_id, settings.mode, settings.polymarket_private_key)
    trader = Trader(pm)
    risk = RiskManager(
        RiskLimits(
            max_total_exposure_usd=settings.max_total_exposure_usd,
            max_order_usd=settings.max_order_usd,
            max_orders_per_hour=settings.max_orders_per_hour,
        )
    )

    if args.once:
        run_cycle(settings, weather, wu, pm, trader, risk, log)
        return

    while True:
        run_cycle(settings, weather, wu, pm, trader, risk, log)
        time.sleep(min(settings.weather_poll_seconds, settings.market_poll_seconds))


if __name__ == "__main__":
    main()
