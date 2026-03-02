# PolyMeteo Trading Bot

Production-oriented Python bot for trading the Polymarket market **"highest temperature in Paris on March 3, 2026"** with strict risk controls and paper mode.

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
python -m src.main --mode live
```

## Environment variables

All runtime knobs are in `.env.example`, including:

- `MODE=paper|live`
- `POLYMARKET_PRIVATE_KEY`, `POLYMARKET_API_KEY`
- `MARKET_ID` or `MARKET_URL`
- `MAX_TOTAL_EXPOSURE_USD`, `MAX_ORDER_USD`, `MAX_ORDERS_PER_HOUR`
- `EDGE_THRESHOLD`, optional `FORECAST_TMAX_C`, `PRIOR_SIGMA_C`
- `STRATEGY_MODE=lock19|legacy`
- `LOCK_TIME_LOCAL`, `LOCK_WINDOW_START_LOCAL`
- `HEDGE_ENABLED`, `HEDGE_RISK_THRESHOLD`, `HEDGE_TREND_HOURS`, `HEDGE_NEAR_PEAK_DELTA_C`
- `HEDGE_MAX_TOTAL_USD` (defaults to 20% of `MAX_TOTAL_EXPOSURE_USD`)
- `HEDGE_ONLY_IF_EDGE_POSITIVE`, `MAIN_ONLY_IF_EDGE_POSITIVE`
- `WEATHER_POLL_SECONDS`, `MARKET_POLL_SECONDS`, `WU_POLL_SECONDS`
- `TIMEZONE=Europe/Paris`

## LOCK@19H + HEDGE strategy

- Before local lock time (`LOCK_TIME_LOCAL`, default `19:00` Europe/Paris), the bot monitors only and does not place the main bet.
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
- Live mode currently requires extending `PolymarketClient.place_limit_order` with signed CLOB order placement using your credentials.
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
