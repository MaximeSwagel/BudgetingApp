from decimal import Decimal

from app.parsers.revolut import parse_revolut_en, parse_revolut_fr


def test_parse_revolut_fr_completed_expense():
    csv_text = (
        "Type,Produit,Date de début,Date de fin,Description,Montant,Frais,Devise,État,Solde\n"
        "CARD_PAYMENT,Current,2026-01-05 10:00:00,2026-01-05 10:00:01,Carrefour,-42.50,0,EUR,TERMINÉ,100.00\n"
    )
    result = parse_revolut_fr(csv_text.encode("utf-8"))

    assert len(result) == 1
    txn = result[0]
    assert txn["description"] == "Carrefour"
    assert txn["original_amount"] == Decimal("-42.50")
    assert txn["original_currency"] == "EUR"
    assert txn["bank"] == "Revolut"
    assert txn["is_expense"] is True
    assert txn["fee"] == Decimal("0")


def test_parse_revolut_fr_skips_non_completed():
    csv_text = (
        "Type,Produit,Date de début,Date de fin,Description,Montant,Frais,Devise,État,Solde\n"
        "CARD_PAYMENT,Current,2026-01-05 10:00:00,,Pending Store,-10.00,0,EUR,EN COURS,100.00\n"
        "CARD_PAYMENT,Current,2026-01-06 10:00:00,2026-01-06 10:00:01,Done Store,-5.00,0,EUR,TERMINÉ,95.00\n"
    )
    result = parse_revolut_fr(csv_text.encode("utf-8"))

    assert len(result) == 1
    assert result[0]["description"] == "Done Store"


def test_parse_revolut_fr_falls_back_to_start_date():
    csv_text = (
        "Type,Produit,Date de début,Date de fin,Description,Montant,Frais,Devise,État,Solde\n"
        "CARD_PAYMENT,Current,2026-02-01 09:30:00,,No End Date,-15.00,0,EUR,TERMINÉ,80.00\n"
    )
    result = parse_revolut_fr(csv_text.encode("utf-8"))

    assert len(result) == 1
    assert result[0]["date"].isoformat().startswith("2026-02-01T09:30:00")


def test_parse_revolut_en_completed_expense():
    csv_text = (
        "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
        "CARD_PAYMENT,Current,2026-01-05 10:00:00,2026-01-05 10:00:01,Tesco,-20.00,0.10,GBP,COMPLETED,150.00\n"
    )
    result = parse_revolut_en(csv_text.encode("utf-8"))

    assert len(result) == 1
    txn = result[0]
    assert txn["description"] == "Tesco"
    assert txn["original_amount"] == Decimal("-20.00")
    assert txn["original_currency"] == "GBP"
    assert txn["bank"] == "Revolut"
    assert txn["is_expense"] is True
    assert txn["fee"] == Decimal("0.10")


def test_parse_revolut_en_income_is_not_expense():
    csv_text = (
        "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
        "TOPUP,Current,2026-01-05 10:00:00,2026-01-05 10:00:01,Salary,1000.00,0,USD,COMPLETED,1000.00\n"
    )
    result = parse_revolut_en(csv_text.encode("utf-8"))

    assert len(result) == 1
    assert result[0]["is_expense"] is False
    assert result[0]["original_amount"] == Decimal("1000.00")


def test_parse_revolut_en_skips_non_completed():
    csv_text = (
        "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
        "CARD_PAYMENT,Current,2026-01-05 10:00:00,,Reverted,-10.00,0,USD,REVERTED,100.00\n"
    )
    result = parse_revolut_en(csv_text.encode("utf-8"))

    assert result == []
