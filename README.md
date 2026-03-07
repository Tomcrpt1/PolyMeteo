# PolyMeteo Trading Bot

Production-oriented Python bot for trading daily Polymarket weather markets (e.g. "highest temperature in Paris on {month}-{day}-{year}") with strict risk controls.

## How it works

1. **Weather ingest**
   - Primary feed: Open-Meteo hourly endpoint around LFPG (CDG coordinates).
   - Open-Meteo calls use a single-day `start_date`/`end_date` window; `forecast_days` is intentionally not used to avoid parameter conflicts.
   - Optional low-frequency Weather Underground parser for a high-so-far sanity check.
2. **Modeling**
   - Gaussian prior centered on `FORECAST_TMAX_C` and `PRIOR_SIGMA_C` (or auto-fetched Open-Meteo daily max when `FORECAST_TMAX_C` is unset).
   - Intraday nowcast clamps probability mass below observed high so far.
   - Late-peak risk score (0..1) from trend, max recency, and diurnal context.
3. **Execution**
   - Pull market token mapping + orderbooks from Polymarket endpoints.
   - Compare model probabilities vs market implied probabilities.
   - Default `lock19` strategy waits until local 19:00, then buys exactly one bucket mapped from the locked max, and optionally adds a single upward hedge for late-peak risk.
   - Optional `legacy` strategy keeps prior adjacent-bucket behavior.
4. **Risk controls**
   - Max total exposure, max order USD, max orders/hour.
   - Kill switch (`KILL_SWITCH=1` or create `./KILL`).

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

## Run

```bash
python -m src.main --mode paper --once
python -m src.main --mode paper
```

> `MODE=live` is intentionally blocked for now with a descriptive error. Paper mode is supported; signed live CLOB execution is not yet integrated.

## Day-by-day usage

For normal daily operation, you usually only change:

- nothing (default auto-rollover), or `TARGET_DATE=YYYY-MM-DD` if you disable rollover

Date behavior is controlled by:

- `AUTO_ROLLOVER_TARGET_DATE=true` (default): bot follows Europe/Paris local calendar date automatically.
- `AUTO_ROLLOVER_TARGET_DATE=false`: bot uses fixed `TARGET_DATE` from config.

Keep these defaults unless you have a custom market naming scheme:

- `MARKET_URL=` (leave empty)
- `MARKET_URL_TEMPLATE=https://polymarket.com/event/highest-temperature-in-paris-on-{month_name}-{day}-{year}`

With those settings, the bot auto-builds the daily Polymarket event URL from `TARGET_DATE` (lowercase English month name and non-zero-padded day).
With `AUTO_ROLLOVER_TARGET_DATE=true`, `TARGET_DATE` is ignored after startup and recomputed from local date each cycle.

## Environment variables

All runtime knobs are in `.env.example`, including:

- `MODE=paper|live`
- `POLYMARKET_PRIVATE_KEY`, `POLYMARKET_API_KEY`
- `MARKET_ID` or `MARKET_URL` (optional; leave empty to auto-build from `TARGET_DATE`)
- `MARKET_URL_TEMPLATE` (default: `https://polymarket.com/event/highest-temperature-in-paris-on-{month_name}-{day}-{year}`)
- `MARKET_CITY_SLUG` (default: `paris`; useful when your template includes `{city_slug}`)
- `MAX_TOTAL_EXPOSURE_USD`, `MAX_ORDER_USD`, `MAX_ORDERS_PER_HOUR`
- `EDGE_THRESHOLD`, optional `FORECAST_TMAX_C`, `PRIOR_SIGMA_C`
- `STRATEGY_MODE=lock19|legacy`
- `LOCK_TIME_LOCAL`, `LOCK_WINDOW_START_LOCAL`
- `HEDGE_ENABLED`, `HEDGE_RISK_THRESHOLD`, `HEDGE_TREND_HOURS`, `HEDGE_NEAR_PEAK_DELTA_C`
- `HEDGE_MAX_TOTAL_USD` (defaults to 20% of `MAX_TOTAL_EXPOSURE_USD`)
- `HEDGE_ONLY_IF_EDGE_POSITIVE`, `MAIN_ONLY_IF_EDGE_POSITIVE`
- `WEATHER_POLL_SECONDS`, `MARKET_POLL_SECONDS`, `WU_POLL_SECONDS`
- `TIMEZONE=Europe/Paris`
- `AUTO_ROLLOVER_TARGET_DATE=true|false`

If `MARKET_URL` is empty and `MARKET_ID` is not set, the bot builds market URL from `TARGET_DATE` using `MARKET_URL_TEMPLATE`.

Recommended lock19 one-bucket setup:

- `LOCK_TIME_LOCAL=17:30`
- `LOCK_WINDOW_START_LOCAL=13:00`
- `MAIN_ONLY_IF_EDGE_POSITIVE=false` (always place the main lock-time bet)
- `HEDGE_ENABLED=false` (pure one-bucket mode)

## LOCK@19H + HEDGE strategy

- Before local lock time (`LOCK_TIME_LOCAL`), the bot monitors only and does not place the main bet.
- At/after lock time, the bot computes `LOCKED_MAX` using hourly records on `TARGET_DATE` from `LOCK_WINDOW_START_LOCAL -> LOCK_TIME_LOCAL`.
- `LOCKED_MAX` is converted to whole °C using `TEMPERATURE_ROUNDING` and mapped to one Polymarket bucket (`<=12`, `13..19`, `>=20`).
- Main position is single-bucket only (no adjacent buckets) and can require positive edge via `MAIN_ONLY_IF_EDGE_POSITIVE=true`.
- Hedge logic only buys the next higher bucket (`bucket+1`) when late-peak conditions trigger (risk score threshold and/or near-peak rising trend), with total cap `HEDGE_MAX_TOTAL_USD`.
- This reflects market resolution on full-day maximum while protecting against rare late-evening new highs.


## Open-Meteo request strategy

- Hourly monitoring: `hourly=temperature_2m,wind_speed_10m,cloud_cover` with `start_date=end_date=TARGET_DATE`.
- Daily prior fallback: `daily=temperature_2m_max` with `start_date=end_date=TARGET_DATE`.
- The bot intentionally does **not** send `forecast_days` in these requests.

## Temperature rounding policy


If `FORECAST_TMAX_C` is empty or omitted, the bot automatically requests Open-Meteo daily `temperature_2m_max` for `TARGET_DATE` at LFPG coordinates and uses that as the prior center.

Resolution is whole °C. Default policy is `round` (`TEMPERATURE_ROUNDING=round`) with configurable `floor` option. Keep this consistent with your interpretation of source data.

## Safety warnings

- Start in paper mode and validate logs before any live mode change.
- Live mode is not yet implemented for execution; `MODE=live` intentionally raises a descriptive runtime error.
- Weather Underground parser is heuristic and should be treated as non-authoritative during intraday updates.
- Final market resolution follows Weather Underground historical daily page and exchange rules.

## Limitations

- WU HTML may change and break parser.
- Open-Meteo is a monitoring proxy, not final resolver.
- This bot avoids aggressive scraping by polling WU at low frequency and caching.

## Testing

```bash
pytest
```

## How to extend

1. Plug ECMWF/GFS blend forecasts into `FORECAST_TMAX_C` dynamically.
2. Use richer late-peak features (radiation, dewpoint spread, cloud motion).
3. Implement live `py-clob-client` signed order submission and order cancel/replace lifecycle.
4. Add persistence (SQLite/Postgres) for audit trails and PnL.
