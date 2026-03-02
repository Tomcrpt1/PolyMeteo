# PolyMeteo Trading Bot

Production-oriented Python bot for trading the Polymarket market **"highest temperature in Paris on March 3, 2026"** with strict risk controls and paper mode.

## How it works

1. **Weather ingest**
   - Primary feed: Open-Meteo hourly endpoint around LFPG (CDG coordinates).
   - Optional low-frequency Weather Underground parser for a high-so-far sanity check.
2. **Modeling**
   - Gaussian prior centered on `FORECAST_TMAX_C` and `PRIOR_SIGMA_C`.
   - Intraday nowcast clamps probability mass below observed high so far.
   - Late-peak risk score (0..1) from trend, max recency, and diurnal context.
3. **Execution**
   - Pull market token mapping + orderbooks from Polymarket endpoints.
   - Compare model probabilities vs market implied probabilities.
   - Buy 1–3 adjacent buckets when edge exceeds threshold and risk limits allow.
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
- `EDGE_THRESHOLD`, `FORECAST_TMAX_C`, `PRIOR_SIGMA_C`
- `WEATHER_POLL_SECONDS`, `MARKET_POLL_SECONDS`, `WU_POLL_SECONDS`
- `TIMEZONE=Europe/Paris`

## Temperature rounding policy

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
