from charset_normalizer import from_bytes


def detect_bank_format(content: bytes) -> str:
    result = from_bytes(content).best()
    text = str(result) if result else content.decode("utf-8", errors="replace")
    first_line = text.split("\n")[0].strip()

    if ";" in first_line and ("Libellé" in first_line or "Débit" in first_line or "Date" in first_line):
        return "ca"
    if "Date de début" in first_line or "Produit" in first_line or "Montant" in first_line:
        return "revolut_fr"
    if "Started Date" in first_line or "Completed Date" in first_line:
        return "revolut_en"
    if first_line.startswith('"') and ("Amoutn" in first_line or "Amount" in first_line):
        return "revolut_merged"

    raise ValueError(f"Unrecognized CSV format. First line: {first_line[:200]}")
