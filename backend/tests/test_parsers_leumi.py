from decimal import Decimal

from app.parsers.detector import detect_bank_format
from app.parsers.leumi import parse_leumi


def _csv(text: str) -> bytes:
    return text.encode("utf-8")


def test_parse_leumi_debit_row():
    csv_text = (
        ",,,,,,\n"
        "Bank Leumi - Account Transactions,,,,,\n"
        "Account Number: 12345-6789,,,,,\n"
        "Date,Description,Reference Number,Debit,Credit,NIS Balance\n"
        "05/01/2026,SUPERMARKET TEL AVIV,123456,150.00,,4850.00\n"
    )
    result = parse_leumi(_csv(csv_text))

    assert len(result) == 1
    txn = result[0]
    assert txn["description"] == "SUPERMARKET TEL AVIV"
    assert txn["original_amount"] == Decimal("-150.00")
    assert txn["is_expense"] is True
    assert txn["original_currency"] == "ILS"
    assert txn["bank"] == "Leumi"
    assert txn["date"].strftime("%Y-%m-%d") == "2026-01-05"


def test_parse_leumi_credit_row():
    csv_text = "Date,Description,Reference Number,Debit,Credit,NIS Balance\n" "06/01/2026,SALARY DEPOSIT,654321,,12000.00,16850.00\n"
    result = parse_leumi(_csv(csv_text))

    assert len(result) == 1
    txn = result[0]
    assert txn["original_amount"] == Decimal("12000.00")
    assert txn["is_expense"] is False


def test_parse_leumi_parses_both_sections():
    csv_text = (
        ",,,,,,\n"
        "Bank Leumi - Account Transactions,,,,,\n"
        "Account Number: 12345-6789,,,,,\n"
        "Balance including Today: 4,850.00,,,,,\n"
        "\n"
        "Today's Transactions,,,,,\n"
        "Date ,Description,Reference Number,Debit,Credit,NIS Balance\n"
        "07/01/2026,COFFEE SHOP,111222,25.00,,4825.00\n"
        "\n"
        "Transactions by Date,,,,,\n"
        "Date,Description,Reference Number,Debit,Credit,NIS Balance\n"
        "05/01/2026,SUPERMARKET TEL AVIV,123456,150.00,,4850.00\n"
        "06/01/2026,SALARY DEPOSIT,654321,,12000.00,16850.00\n"
        "\n"
        "*Balance does not include pending transactions,,,,,\n"
    )
    result = parse_leumi(_csv(csv_text))

    descriptions = {txn["description"] for txn in result}
    assert len(result) == 3
    assert descriptions == {"COFFEE SHOP", "SUPERMARKET TEL AVIV", "SALARY DEPOSIT"}


def test_parse_leumi_skips_preamble_and_noise_lines():
    csv_text = (
        ",,,,,,\n"
        "Bank Leumi - Account Transactions,,,,,\n"
        "Account Number: 12345-6789,,,,,\n"
        "Balance including Today: 4,850.00,,,,,\n"
        "\n"
        "Transactions by Date,,,,,\n"
        "Date,Description,Reference Number,Debit,Credit,NIS Balance\n"
        "05/01/2026,SUPERMARKET TEL AVIV,123456,150.00,,4850.00\n"
        "\n"
        "*Balance does not include pending transactions,,,,,\n"
    )
    result = parse_leumi(_csv(csv_text))

    assert len(result) == 1
    assert result[0]["description"] == "SUPERMARKET TEL AVIV"


def test_parse_leumi_preserves_quoted_comma_description():
    csv_text = "Date,Description,Reference Number,Debit,Credit,NIS Balance\n" '08/01/2026,"RAMI LEVY, TEL AVIV BRANCH",789012,88.40,,4761.60\n'
    result = parse_leumi(_csv(csv_text))

    assert len(result) == 1
    assert result[0]["description"] == "RAMI LEVY, TEL AVIV BRANCH"


def test_parse_leumi_thousands_separator_amount():
    csv_text = 'Date,Description,Reference Number,Debit,Credit,NIS Balance\n' '09/01/2026,RENT PAYMENT,345678,"1,234.56",,3527.04\n'
    result = parse_leumi(_csv(csv_text))

    assert len(result) == 1
    assert result[0]["original_amount"] == Decimal("-1234.56")
    assert result[0]["is_expense"] is True


def test_detect_bank_format_returns_leumi_for_second_line_marker():
    csv_text = (
        ",,,,,,\n"
        "Bank Leumi - Account Transactions,,,,,\n"
        "Account Number: 12345-6789,,,,,\n"
        "Date,Description,Reference Number,Debit,Credit,NIS Balance\n"
        "05/01/2026,SUPERMARKET TEL AVIV,123456,150.00,,4850.00\n"
    )
    assert detect_bank_format(_csv(csv_text)) == "leumi"


def test_detect_bank_format_still_detects_ca():
    csv_text = "Date;Libelle;Debit;Credit\n05/01/2026;CARREFOUR MARKET;42,50;\n"
    assert detect_bank_format(csv_text.encode("utf-8")) == "ca"
