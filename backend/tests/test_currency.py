from decimal import Decimal

import httpx
import pytest

from app.services import currency


@pytest.fixture(autouse=True)
def clear_rate_cache():
    currency._rate_cache.clear()
    yield
    currency._rate_cache.clear()


@pytest.mark.asyncio
async def test_get_exchange_rate_same_currency_is_one():
    rate = await currency.get_exchange_rate("EUR", "EUR")
    assert rate == Decimal("1")


@pytest.mark.asyncio
async def test_get_exchange_rate_uses_frankfurter_response(monkeypatch):
    async def fake_get(self, url, params=None, **kwargs):
        assert params == {"from": "EUR", "to": "USD"}
        return httpx.Response(200, json={"rates": {"USD": 1.1}}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    rate = await currency.get_exchange_rate("EUR", "USD")
    assert rate == Decimal("1.1")


@pytest.mark.asyncio
async def test_get_exchange_rate_caches_result(monkeypatch):
    call_count = 0

    async def fake_get(self, url, params=None, **kwargs):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"rates": {"USD": 1.2}}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    rate1 = await currency.get_exchange_rate("EUR", "USD", "2026-01-01")
    rate2 = await currency.get_exchange_rate("EUR", "USD", "2026-01-01")

    assert rate1 == rate2 == Decimal("1.2")
    assert call_count == 1


@pytest.mark.asyncio
async def test_get_exchange_rate_falls_back_when_api_fails(monkeypatch):
    async def fake_get(self, url, params=None, **kwargs):
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    rate = await currency.get_exchange_rate("EUR", "ILS")
    assert rate == Decimal("3.61")


@pytest.mark.asyncio
async def test_get_exchange_rate_ils_routes_via_usd(monkeypatch):
    async def fake_get(self, url, params=None, **kwargs):
        rates = {"EUR": {"USD": 1.1}, "ILS": {"USD": 0.28}}
        return httpx.Response(
            200, json={"rates": {"USD": rates[params["from"]]["USD"]}}, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    rate = await currency.get_exchange_rate("EUR", "ILS")
    assert rate == Decimal("1.1") / Decimal("0.28")


@pytest.mark.asyncio
async def test_convert_amount_applies_rate_and_rounds(monkeypatch):
    async def fake_get_exchange_rate(from_currency, to_currency, date_str=None):
        return Decimal("2")

    monkeypatch.setattr(currency, "get_exchange_rate", fake_get_exchange_rate)

    converted, rate = await currency.convert_amount(Decimal("10.005"), "USD", "EUR")
    assert rate == Decimal("2")
    assert converted == Decimal("20.01")
