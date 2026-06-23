import logging
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

_rate_cache: dict[str, Decimal] = {}


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
            if from_currency == "ILS" or to_currency == "ILS":
                resp_from = await client.get(url, params={"from": from_currency, "to": "USD"})
                resp_to = await client.get(url, params={"from": to_currency, "to": "USD"})
                if resp_from.status_code == 200 and resp_to.status_code == 200:
                    from_usd = Decimal(str(resp_from.json()["rates"]["USD"]))
                    to_usd = Decimal(str(resp_to.json()["rates"]["USD"]))
                    rate = from_usd / to_usd
                    _rate_cache[cache_key] = rate
                    return rate

            resp = await client.get(url, params={"from": from_currency, "to": to_currency})
            if resp.status_code == 200:
                data = resp.json()
                rate = Decimal(str(data["rates"][to_currency]))
                _rate_cache[cache_key] = rate
                return rate
    except Exception as e:
        logger.error(f"Currency conversion failed: {e}")

    fallback_rates = {
        ("EUR", "ILS"): Decimal("3.61"),
        ("USD", "ILS"): Decimal("3.13"),
        ("DKK", "ILS"): Decimal("0.48"),
        ("ILS", "EUR"): Decimal("0.277"),
        ("ILS", "USD"): Decimal("0.319"),
        ("ILS", "DKK"): Decimal("2.08"),
    }
    rate = fallback_rates.get((from_currency, to_currency), Decimal("1"))
    _rate_cache[cache_key] = rate
    return rate


async def convert_amount(amount: Decimal, from_currency: str, to_currency: str, date_str: str | None = None) -> tuple[Decimal, Decimal]:
    rate = await get_exchange_rate(from_currency, to_currency, date_str)
    converted = (amount * rate).quantize(Decimal("0.01"))
    return converted, rate
