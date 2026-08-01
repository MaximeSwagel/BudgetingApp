"""Merchant-key normalization, matching, and correction-aware categorization.

Design decisions (see the plan for the full rationale):

- D-02: corrections are resolved deterministically *before* the AI call --
  matched transactions never reach the provider. This is simpler and cheaper
  than injecting corrections into the prompt as few-shot examples, and it
  works even with no API key configured.
- D-03: `categorize_transactions(transactions)` keeps its exact current
  signature so the existing monkeypatches in the categorizer test suites
  stay effective. `categorize_with_corrections` below takes the AI callable
  as a parameter (dependency injection) instead of importing it directly, so
  each router passes its own module-global `categorize_transactions` name.
"""

import re

from app.services.categorizer import UNCATEGORIZED

# Bounds how broadly a stored merchant key may match by containment: a key
# shorter than this could show up inside unrelated descriptions and silently
# mis-teach every future transaction that happens to contain it.
MIN_KEY_LEN = 4

# `\w` is unicode-aware for `str` patterns in Python 3 by default, so Hebrew
# and accented-Latin letters survive this substitution. An ASCII-only
# character class would erase them entirely and collapse every non-ASCII
# merchant onto the same empty key.
_NON_WORD_SPACE = re.compile(r"[^\w\s]", re.UNICODE)
_DIGIT_RUN = re.compile(r"\d+")
_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_merchant(description: str) -> str:
    """Reduce a raw transaction description to a stable merchant key.

    Casefold, replace punctuation with spaces, strip digit runs (dates,
    reference numbers), collapse whitespace, and truncate to fit the
    `merchant_key` column. Returns "" when nothing identifying remains --
    callers must treat "" as unusable and never store or match on it.
    """
    text = description.casefold()
    text = _NON_WORD_SPACE.sub(" ", text)
    text = _DIGIT_RUN.sub(" ", text)
    text = _WHITESPACE_RUN.sub(" ", text).strip()
    return text[:200]


def match_key(description: str, keys) -> str | None:
    """Find the stored merchant key that best matches a description.

    `keys` is any iterable of merchant_key strings (a dict is iterated over
    its keys). Returns the exact normalized key when present, else the
    longest stored key of at least MIN_KEY_LEN characters contained in the
    normalized description, else None. This is the single matching
    implementation shared by the categorization path and the read-time badge
    computation, so the badge always tells the truth about what the
    categorizer will do.
    """
    normalized = normalize_merchant(description)
    if not normalized:
        return None

    if normalized in keys:
        return normalized

    candidates = [key for key in keys if len(key) >= MIN_KEY_LEN and key in normalized]
    if not candidates:
        return None
    return max(candidates, key=len)


def learned_categories(corrections: dict) -> dict[str, dict]:
    """Build a merchant_key -> {general_category, precise_category} mapping
    from a merchant_key-to-CategoryCorrection dict, skipping flag-only
    entries (category is None). Emitting the same shape the AI providers
    emit means the existing `resolve_category_id` helper consumes
    corrections with no special-casing downstream."""
    result: dict[str, dict] = {}
    for key, correction in corrections.items():
        if correction.category is None:
            continue
        result[key] = {
            "general_category": correction.category.group.name,
            "precise_category": correction.category.name,
        }
    return result


async def categorize_with_corrections(transactions: list[dict], learned: dict, ai_categorize) -> list[dict]:
    """Categorize `transactions`, resolving known merchants from `learned`
    and falling back to `ai_categorize` (an async callable, injected rather
    than imported -- see D-03) only for the ones left unmatched.

    Preserves the caller's ordering: the result list is the same length as
    `transactions` and each index lines up with the input, so `zip(txns,
    results)` at the call site works unchanged.
    """
    results: list[dict | None] = [None] * len(transactions)
    pending: list[dict] = []
    pending_indices: list[int] = []

    for idx, txn in enumerate(transactions):
        key = match_key(txn["description"], learned)
        if key is not None:
            results[idx] = learned[key]
        else:
            pending.append(txn)
            pending_indices.append(idx)

    if pending:
        ai_results = await ai_categorize(pending)
        for idx, result in zip(pending_indices, ai_results):
            results[idx] = result

    return [r if r is not None else dict(UNCATEGORIZED) for r in results]
