from __future__ import annotations

import logging
from collections.abc import Mapping

import httpx

from src.polymarket.models import LimitOrderRequest, OutcomeBook
from src.strategy.buckets import normalize_distribution
from src.utils.retry import network_retry


class PolymarketClient:
    def __init__(self, market_id: str | None, mode: str, private_key: str | None = None):
        self.market_id = market_id
        self.mode = mode
        self.private_key = private_key
        self.log = logging.getLogger("polymeteo")
        self.http = httpx.Client(timeout=15)

    @network_retry
    def fetch_market_tokens(self) -> dict[str, str]:
        if not self.market_id:
            raise ValueError("market_id required to fetch tokens")
        url = f"https://gamma-api.polymarket.com/markets/{self.market_id}"
        data = self.http.get(url).json()
        outcomes = data.get("outcomes") or []
        clob_ids = data.get("clobTokenIds") or []
        mapping: dict[str, str] = {}
        for label, token_id in zip(outcomes, clob_ids):
            clean = str(label).replace("°C", "").replace(" ", "")
            if clean in {"12orbelow", "<=12"}:
                mapping["<=12"] = str(token_id)
            elif clean in {"20orabove", ">=20"}:
                mapping[">=20"] = str(token_id)
            else:
                mapping[clean] = str(token_id)
        return mapping

    @network_retry
    def fetch_orderbooks(self, token_map: Mapping[str, str]) -> dict[str, OutcomeBook]:
        books: dict[str, OutcomeBook] = {}
        for outcome, token_id in token_map.items():
            endpoint = f"https://clob.polymarket.com/book?token_id={token_id}"
            payload = self.http.get(endpoint).json()
            bids = payload.get("bids", [])
            asks = payload.get("asks", [])
            best_bid = float(bids[0]["price"]) if bids else 0.0
            best_ask = float(asks[0]["price"]) if asks else 0.0
            books[outcome] = OutcomeBook(outcome=outcome, token_id=token_id, best_bid=best_bid, best_ask=best_ask)
        return books

    def implied_probabilities(self, books: Mapping[str, OutcomeBook]) -> dict[str, float]:
        mids = {k: max(0.001, min(0.999, v.mid)) for k, v in books.items()}
        return normalize_distribution(mids)

    def place_limit_order(self, req: LimitOrderRequest) -> str:
        if self.mode == "paper":
            self.log.info("[paper] place order outcome=%s price=%.3f size=%.2f", req.outcome, req.price, req.size_usd)
            return f"paper-{req.outcome}-{req.price:.3f}"
        # Live path intentionally minimal and compatible with py-clob-client setup outside this repository.
        raise NotImplementedError("Live trading wiring should use py-clob-client credentials and signing")
