import csv
import io
import re
from datetime import datetime
from decimal import Decimal

from charset_normalizer import from_bytes

DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def parse_leumi(content: bytes) -> list[dict]:
    result = from_bytes(content).best()
    text = str(result) if result else content.decode("latin-1", errors="replace")
    text = text.replace("\r\n", "\n")

    reader = csv.reader(io.StringIO(text))

    transactions = []

    for row in reader:
        if not row:
            continue

        date_str = row[0].strip()
        if not DATE_RE.match(date_str):
            # Skips preamble/metadata lines, both header-row occurrences
            # ("Date ,Description,..." and "Date,Description,..."), section
            # labels ("Today's Transactions" / "Transactions by Date"), blank
            # lines, and the trailing "*" disclaimer line -- all in one rule.
            continue

        if len(row) < 5:
            continue

        try:
            date = datetime.strptime(date_str, "%d/%m/%Y")
        except ValueError:
            continue

        description = row[1].strip()
        debit_str = row[3].strip().replace(",", "")
        credit_str = row[4].strip().replace(",", "")

        if debit_str:
            try:
                amount = -abs(Decimal(debit_str))
                is_expense = True
            except Exception:
                continue
        elif credit_str:
            try:
                amount = Decimal(credit_str)
                is_expense = False
            except Exception:
                continue
        else:
            continue

        transactions.append({
            "date": date,
            "description": description,
            "original_amount": amount,
            "original_currency": "ILS",
            "bank": "Leumi",
            "is_expense": is_expense,
        })

    return transactions
