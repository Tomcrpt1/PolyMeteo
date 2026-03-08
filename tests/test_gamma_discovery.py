from src.polymarket.clob_client import PolymarketClient


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeHTTP:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, params=None):
        params = params or {}
        key = (url, tuple(sorted(params.items())))
        self.calls.append(key)
        return FakeResponse(self.routes.get(key, []))


def _gamma_url(path: str) -> str:
    return f"https://gamma-api.polymarket.com/{path}"


def test_discover_market_direct_slug_lookup_success():
    slug = "highest-temperature-in-paris-on-march-8-2026"
    routes = {
        (_gamma_url("markets"), (("slug", slug),)): [{"id": "m1", "slug": slug, "question": "Highest temperature in Paris on March 8, 2026"}],
    }
    client = PolymarketClient(market_id=None, mode="paper", market_url=f"https://polymarket.com/event/{slug}")
    client.http = FakeHTTP(routes)

    resolved = client.discover_market_via_gamma(client.market_url)

    assert resolved.market_id == "m1"
    assert resolved.source == "markets?slug"


def test_discover_market_fallback_when_direct_slug_empty():
    slug = "highest-temperature-in-paris-on-march-8-2026"
    routes = {
        (_gamma_url("markets"), (("slug", slug),)): [],
        (_gamma_url("events"), (("slug", slug),)): [{"id": "e1", "title": "Paris weather", "slug": "paris-weather", "markets": [{"id": "m2", "question": "Highest temperature in Paris on March 8, 2026", "slug": slug}]}],
        (_gamma_url("markets"), (("search", slug),)): [],
        (_gamma_url("events"), (("search", "highest temperature in paris on march 8 2026"),)): [],
    }
    client = PolymarketClient(market_id=None, mode="paper", market_url=f"https://polymarket.com/event/{slug}")
    client.http = FakeHTTP(routes)

    resolved = client.discover_market_via_gamma(client.market_url)

    assert resolved.market_id == "m2"
    assert resolved.source == "fallback"


def test_discover_market_strips_fragment_from_event_url():
    slug = "highest-temperature-in-paris-on-march-8-2026"
    routes = {
        (_gamma_url("markets"), (("slug", slug),)): [{"id": "m1", "slug": slug}],
    }
    client = PolymarketClient(market_id=None, mode="paper")
    client.http = FakeHTTP(routes)

    resolved = client.discover_market_via_gamma(f"https://polymarket.com/event/{slug}#4RSocrb")

    assert resolved.market_id == "m1"


def test_discover_market_multiple_candidates_selects_paris_target_date():
    slug = "highest-temperature-in-paris-on-march-8-2026"
    routes = {
        (_gamma_url("markets"), (("slug", slug),)): [],
        (_gamma_url("events"), (("slug", slug),)): [],
        (_gamma_url("markets"), (("search", slug),)): [
            {"id": "wrong-date", "question": "Highest temperature in Paris on March 7, 2026", "slug": "highest-temperature-in-paris-on-march-7-2026"},
            {"id": "wrong-city", "question": "Highest temperature in London on March 8, 2026", "slug": "highest-temperature-in-london-on-march-8-2026"},
            {"id": "best", "question": "Highest temperature in Paris on March 8, 2026", "slug": slug},
        ],
        (_gamma_url("events"), (("search", "highest temperature in paris on march 8 2026"),)): [],
    }
    client = PolymarketClient(market_id=None, mode="paper")
    client.http = FakeHTTP(routes)

    resolved = client.discover_market_via_gamma(f"https://polymarket.com/event/{slug}")

    assert resolved.market_id == "best"


def test_discover_market_failure_has_clear_error():
    slug = "highest-temperature-in-paris-on-march-8-2026"
    routes = {
        (_gamma_url("markets"), (("slug", slug),)): [],
        (_gamma_url("events"), (("slug", slug),)): [],
        (_gamma_url("markets"), (("search", slug),)): [],
        (_gamma_url("events"), (("search", "highest temperature in paris on march 8 2026"),)): [],
    }
    client = PolymarketClient(market_id=None, mode="paper")
    client.http = FakeHTTP(routes)

    try:
        client.discover_market_via_gamma(f"https://polymarket.com/event/{slug}")
        raise AssertionError("Expected discovery failure")
    except ValueError as exc:
        message = str(exc)
        assert "slug=highest-temperature-in-paris-on-march-8-2026" in message
        assert "primary markets?slug returned 0 results" in message
        assert "attempts=" in message
