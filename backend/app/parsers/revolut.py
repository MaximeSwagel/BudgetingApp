import csv
import io
from datetime import datetime
from decimal import Decimal

from charset_normalizer import from_bytes


def _decode(content: bytes) -> str:
    result = from_bytes(content).best()
    return str(result) if result else content.decode("utf-8", errors="replace")


def parse_revolut_fr(content: bytes) -> list[dict]:
    text = _decode(content)
    reader = csv.DictReader(io.StringIO(text))
    transactions = []

    for row in reader:
        state = row.get("État", "").strip().upper()
        if state != "TERMINÉ":
            continue

        amount_str = row.get("Montant", "0").strip()
        amount = Decimal(amount_str)

        completed_date_str = row.get("Date de fin", "").strip()
        try:
            date = datetime.strptime(completed_date_str[:19], "%Y-%m-%d %H:%M:%S")
        except (ValueError, IndexError):
            start_date_str = row.get("Date de début", "").strip()
            date = datetime.strptime(start_date_str[:19], "%Y-%m-%d %H:%M:%S")

        description = row.get("Description", "").strip()
        currency = row.get("Devise", "").strip()
        fee_str = row.get("Frais", "0").strip()
        fee = Decimal(fee_str) if fee_str else Decimal("0")

        transactions.append({
            "date": date,
            "description": description,
            "original_amount": amount,
            "original_currency": currency,
            "bank": "Revolut",
            "is_expense": amount < 0,
            "fee": fee,
        })

    return transactions


def parse_revolut_en(content: bytes) -> list[dict]:
    text = _decode(content)
    reader = csv.DictReader(io.StringIO(text))
    transactions = []

    for row in reader:
        state = row.get("State", "").strip().upper()
        if state != "COMPLETED":
            continue

        amount_str = row.get("Amount", "0").strip()
        amount = Decimal(amount_str)

        completed_date_str = row.get("Completed Date", "").strip()
        try:
            date = datetime.strptime(completed_date_str[:19], "%Y-%m-%d %H:%M:%S")
        except (ValueError, IndexError):
            start_date_str = row.get("Started Date", "").strip()
            date = datetime.strptime(start_date_str[:19], "%Y-%m-%d %H:%M:%S")

        description = row.get("Description", "").strip()
        currency = row.get("Currency", "").strip()
        fee_str = row.get("Fee", "0").strip()
        fee = Decimal(fee_str) if fee_str else Decimal("0")

        transactions.append({
            "date": date,
            "description": description,
            "original_amount": amount,
            "original_currency": currency,
            "bank": "Revolut",
            "is_expense": amount < 0,
            "fee": fee,
        })

    return transactions
