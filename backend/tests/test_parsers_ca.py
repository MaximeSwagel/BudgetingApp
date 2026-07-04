from decimal import Decimal

from app.parsers.ca import parse_credit_agricole


def test_parse_credit_agricole_debit_and_credit():
    csv_text = (
        "Date;Libelle;Debit;Credit\n"
        "05/01/2026;CARREFOUR MARKET;42,50;\n"
        "06/01/2026;VIREMENT SALAIRE;;1500,00\n"
    )
    result = parse_credit_agricole(csv_text.encode("utf-8"))

    assert len(result) == 2

    debit = result[0]
    assert debit["description"] == "CARREFOUR MARKET"
    assert debit["original_amount"] == Decimal("-42.50")
    assert debit["is_expense"] is True
    assert debit["original_currency"] == "EUR"
    assert debit["bank"] == "CA"
    assert debit["date"].strftime("%Y-%m-%d") == "2026-01-05"

    credit = result[1]
    assert credit["description"] == "VIREMENT SALAIRE"
    assert credit["original_amount"] == Decimal("1500.00")
    assert credit["is_expense"] is False


def test_parse_credit_agricole_merges_wrapped_lines():
    csv_text = (
        "Date;Libelle;Debit;Credit\n"
        "05/01/2026;CARREFOUR MARKET\n"
        "PARIS FR;42,50;\n"
    )
    result = parse_credit_agricole(csv_text.encode("utf-8"))

    assert len(result) == 1
    assert result[0]["description"] == "CARREFOUR MARKET PARIS FR"


def test_parse_credit_agricole_returns_empty_for_unrecognized_header():
    csv_text = "Not;A;Recognized;Header\nfoo;bar;baz;qux\n"
    result = parse_credit_agricole(csv_text.encode("utf-8"))

    assert result == []


def test_parse_credit_agricole_skips_lines_without_valid_date():
    csv_text = (
        "Date;Libelle;Debit;Credit\n"
        "not-a-date;Garbage row;10,00;\n"
        "07/01/2026;Valid row;5,00;\n"
    )
    result = parse_credit_agricole(csv_text.encode("utf-8"))

    assert len(result) == 1
    assert result[0]["description"] == "Valid row"
