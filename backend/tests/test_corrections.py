from app.services.corrections import match_key, normalize_merchant


def test_normalize_merchant_ignores_case_punctuation_and_digits():
    a = normalize_merchant("SUPER-YUDA  TLV 12/03/26")
    b = normalize_merchant("super yuda tlv")
    assert a == b
    assert a != ""


def test_normalize_merchant_preserves_non_ascii_letters():
    # Bank Leumi is an Israeli bank; an ASCII-only filter would collapse
    # every Hebrew merchant onto the same empty key.
    hebrew_key = normalize_merchant("סופר יודה")
    accented_key = normalize_merchant("Café Rüdesheimer")
    assert hebrew_key != ""
    assert accented_key != ""


def test_normalize_merchant_returns_empty_when_nothing_identifying_remains():
    assert normalize_merchant("  12/03  ") == ""


def test_match_key_containment():
    assert match_key("SUPER YUDA TEL AVIV", {"super yuda": object()}) == "super yuda"


def test_match_key_rejects_short_candidate_by_containment():
    # "xyz" (3 chars) is below MIN_KEY_LEN and must never match by
    # containment, even though it appears inside the normalized description.
    assert match_key("XYZ CORP LTD", {"xyz": object()}) is None


def test_match_key_prefers_longer_candidate_when_multiple_match():
    keys = {"super": object(), "super yuda": object()}
    assert match_key("super yuda tel aviv", keys) == "super yuda"
