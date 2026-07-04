import logging
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

_rate_cache: dict[str, Decimal] = {}

# Rough emergency-only USD valuations, used solely when the live Frankfurter
# API call fails. Built from string literals to stay consistent with the
# app's Decimal money convention (never from float).
_FALLBACK_TO_USD: dict[str, Decimal] = {
    "USD": Decimal("1"),
    "EUR": Decimal("1.08"),
    "ILS": Decimal("0.27"),
    "DKK": Decimal("0.145"),
}


def _fallback_rate(from_currency: str, to_currency: str) -> Decimal:
    if from_currency in _FALLBACK_TO_USD and to_currency in _FALLBACK_TO_USD:
        return _FALLBACK_TO_USD[from_currency] / _FALLBACK_TO_USD[to_currency]
    logger.error(f"No fallback rate available for unsupported currency pair: {from_currency}->{to_currency}")
    return Decimal("1")


async def get_exchange_rate(from_currency: str, to_currency: str, date_str: str | None = None) -> Decimal:
    if from_currency == to_currency:
        return Decimal("1")

    cache_key = f"{from_currency}_{to_currency}_{date_str or 'latest'}"
    if cache_key in _rate_cache:
        return _rate_cache[cache_key]

    url = "https://api.frankfurter.dev/v1/latest"
    if date_str:
        url = f"https://api.frankfurter.dev/v1/{date_str}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params={"from": from_currency, "to": to_currency})
            if resp.status_code == 200:
                data = resp.json()
                rate = Decimal(str(data["rates"][to_currency]))
                _rate_cache[cache_key] = rate
                return rate
    except Exception as e:
        logger.error(f"Currency conversion failed: {e}")

    rate = _fallback_rate(from_currency, to_currency)
    _rate_cache[cache_key] = rate
    return rate


async def convert_amount(amount: Decimal, from_currency: str, to_currency: str, date_str: str | None = None) -> tuple[Decimal, Decimal]:
    rate = await get_exchange_rate(from_currency, to_currency, date_str)
    converted = (amount * rate).quantize(Decimal("0.01"))
    return converted, rate
