import re
from datetime import datetime
from decimal import Decimal

from charset_normalizer import from_bytes

DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}")


def parse_credit_agricole(content: bytes) -> list[dict]:
    result = from_bytes(content).best()
    text = str(result) if result else content.decode("latin-1", errors="replace")

    raw_lines = text.replace("\r\n", "\n").split("\n")

    merged_lines: list[str] = []
    for line in raw_lines:
        if not line.strip():
            continue
        if DATE_RE.match(line.strip()) or line.strip().lower().startswith("date"):
            merged_lines.append(line.strip())
        elif merged_lines:
            merged_lines[-1] = merged_lines[-1] + " " + line.strip()

    if not merged_lines:
        return []

    header = merged_lines[0]
    if "Libellé" not in header and "Date" not in header:
        return []

    transactions = []

    for line in merged_lines[1:]:
        parts = line.split(";")
        if len(parts) < 3:
            continue

        date_str = parts[0].strip().strip('"')
        if not DATE_RE.match(date_str):
            continue

        date = datetime.strptime(date_str, "%d/%m/%Y")

        label = parts[1].strip().strip('"')
        label = re.sub(r"\s+", " ", label).strip()

        debit_str = parts[2].strip().strip('"').replace(",", ".") if len(parts) > 2 else ""
        credit_str = parts[3].strip().strip('"').replace(",", ".") if len(parts) > 3 else ""

        if debit_str and debit_str != "":
            try:
                amount = -abs(Decimal(debit_str))
                is_expense = True
            except Exception:
                continue
        elif credit_str and credit_str != "":
            try:
                amount = Decimal(credit_str)
                is_expense = False
            except Exception:
                continue
        else:
            continue

        transactions.append({
            "date": date,
            "description": label,
            "original_amount": amount,
            "original_currency": "EUR",
            "bank": "CA",
            "is_expense": is_expense,
        })

    return transactions
