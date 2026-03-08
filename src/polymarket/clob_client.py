from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from src.polymarket.models import LimitOrderRequest, OutcomeBook
from src.strategy.buckets import normalize_distribution
from src.utils.retry import network_retry


class PolymarketClient:
    def __init__(self, market_id: str | None, mode: str, private_key: str | None = None, market_url: str | None = None):
        self.market_id = market_id
        self.market_url = market_url
        self.mode = mode
        self.private_key = private_key
        self.log = logging.getLogger("polymeteo")
        self.http = httpx.Client(timeout=15)

    @dataclass(slots=True)
    class ResolvedGammaMarket:
        market_id: str
        event_id: str | None
        title: str | None
        slug: str | None
        source: str

    def _parse_event_slug(self, market_url: str) -> str:
        slug = urlparse(market_url.split("#", maxsplit=1)[0]).path.rstrip("/").split("/")[-1]
        if not slug:
            raise ValueError(f"Unable to parse market slug from MARKET_URL={market_url}")
        return slug

    def _gamma_get(self, endpoint: str, params: dict[str, str]) -> list[dict]:
        response = self.http.get(f"https://gamma-api.polymarket.com/{endpoint}", params=params)
        data = response.json()
        if isinstance(data, list):
            return data
        return [data] if isinstance(data, dict) else []

    def _extract_markets_from_events(self, events: list[dict]) -> list[dict]:
        markets: list[dict] = []
        for event in events:
            nested = event.get("markets") or []
            for market in nested:
                if isinstance(market, dict):
                    markets.append(
                        {
                            **market,
                            "_event_id": event.get("id"),
                            "_event_title": event.get("title") or event.get("name"),
                            "_event_slug": event.get("slug"),
                        }
                    )
        return markets

    @staticmethod
    def _date_fragment(text: str | None) -> str | None:
        if not text:
            return None
        match = re.search(
            r"(january|february|march|april|may|june|july|august|september|october|november|december)-\d{1,2}-\d{4}",
            text.lower(),
        )
        return match.group(0) if match else None

    def _candidate_score(self, candidate: dict, desired_slug: str) -> int:
        desired_slug_l = desired_slug.lower()
        desired_date = self._date_fragment(desired_slug_l)

        slug = str(candidate.get("slug") or candidate.get("_event_slug") or "").lower()
        title = str(candidate.get("question") or candidate.get("title") or candidate.get("_event_title") or "").lower()
        text = f"{slug} {title}"

        score = 0
        if slug == desired_slug_l:
            score += 100
        if desired_slug_l in text:
            score += 30
        if desired_date and desired_date in text:
            score += 25
        if "paris" in text:
            score += 10
        if "highest" in text and "temperature" in text:
            score += 10
        return score

    def _select_best_candidate(self, candidates: list[dict], desired_slug: str) -> dict | None:
        ranked = sorted(
            candidates,
            key=lambda c: (self._candidate_score(c, desired_slug), str(c.get("id") or "")),
            reverse=True,
        )
        if not ranked:
            return None
        if self._candidate_score(ranked[0], desired_slug) <= 0:
            return None
        return ranked[0]

    def discover_market_via_gamma(self, market_url: str) -> ResolvedGammaMarket:
        slug = self._parse_event_slug(market_url)
        self.log.info("gamma discovery: event_url=%s slug=%s", market_url, slug)

        primary = self._gamma_get("markets", {"slug": slug})
        self.log.info("gamma discovery: primary markets?slug results=%d", len(primary))
        selected = self._select_best_candidate(primary, slug)
        if selected:
            market_id = selected.get("id")
            if market_id:
                return self.ResolvedGammaMarket(
                    market_id=str(market_id),
                    event_id=str(selected.get("eventId")) if selected.get("eventId") else None,
                    title=str(selected.get("question") or selected.get("title")) if (selected.get("question") or selected.get("title")) else None,
                    slug=str(selected.get("slug")) if selected.get("slug") else None,
                    source="markets?slug",
                )

        attempts = ["markets?slug"]
        fallback_candidates: list[dict] = []
        for endpoint, params in [
            ("events", {"slug": slug}),
            ("markets", {"search": slug}),
            ("events", {"search": slug.replace("-", " ")}),
        ]:
            attempts.append(f"{endpoint}?{','.join(params.keys())}")
            rows = self._gamma_get(endpoint, params)
            if endpoint == "events":
                rows = self._extract_markets_from_events(rows)
            fallback_candidates.extend(rows)

        self.log.info("gamma discovery: fallback candidates=%d", len(fallback_candidates))
        selected = self._select_best_candidate(fallback_candidates, slug)
        if selected and selected.get("id"):
            resolved = self.ResolvedGammaMarket(
                market_id=str(selected.get("id")),
                event_id=str(selected.get("eventId") or selected.get("_event_id")) if (selected.get("eventId") or selected.get("_event_id")) else None,
                title=str(selected.get("question") or selected.get("title") or selected.get("_event_title"))
                if (selected.get("question") or selected.get("title") or selected.get("_event_title"))
                else None,
                slug=str(selected.get("slug") or selected.get("_event_slug")) if (selected.get("slug") or selected.get("_event_slug")) else None,
                source="fallback",
            )
            self.log.info("gamma discovery: selected market_id=%s title=%s source=%s", resolved.market_id, resolved.title, resolved.source)
            return resolved

        raise ValueError(
            f"Could not resolve market via gamma for slug={slug}. "
            f"primary markets?slug returned {len(primary)} results; attempts={attempts}."
        )

    @network_retry
    def fetch_market_tokens(self) -> dict[str, str]:
        if not self.market_id:
            if not self.market_url:
                raise ValueError("market_url required to resolve market_id")
            resolved = self.discover_market_via_gamma(self.market_url)
            self.market_id = resolved.market_id
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
        raise RuntimeError(
            "Live mode order placement is not implemented yet. "
            "Please run with MODE=paper until signed CLOB execution is integrated."
        )

    def sync_or_cancel_open_orders_for_rollover(self, open_order_ids: list[str]) -> None:
        if self.mode == "paper":
            return
        raise RuntimeError(
            "Live rollover order sync/cancellation is not implemented yet. "
            "Cannot safely rollover with existing live open orders."
        )
