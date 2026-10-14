"""Comp quality filters shared by the MCP server and the niche screener."""

import re

# Titles that are not a single comparable item: multi-item lots, parts/repair,
# accessories sold on their own, and non-menswear sizing.
JUNK_TITLE_TERMS = [
    "lot", "lots", "bundle", "parts", "repair", "damaged", "as is", "as-is",
    "insoles", "laces", "box only", "empty box", "dust bag only",
    "women", "womens", "women's", "ladies", "kids", "boys", "girls", "youth",
    "toddler", "baby", "replica", "shoe tree", "shoe trees", "catalog", "sticker",
    "keychain",
]

def _terms_re(terms: list[str]) -> re.Pattern:
    return re.compile(r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b", re.IGNORECASE)


_JUNK_RE = _terms_re(JUNK_TITLE_TERMS)


def normalize_title(text: str) -> str:
    """Lowercase and drop apostrophes so "Tricker's" matches "Trickers"."""
    return re.sub(r"['’`]", "", text.lower())


def matches_brand(title: str, brand: str | list[str]) -> bool:
    aliases = [brand] if isinstance(brand, str) else brand
    norm = normalize_title(title)
    return any(normalize_title(a) in norm for a in aliases if a)


def filter_by_brand(comps: list, brand: str | list[str]) -> list:
    if not brand:
        return comps
    return [c for c in comps if matches_brand(c.title, brand)]


def is_junk_title(
    title: str, extra_terms: list[str] | None = None, keep_terms: list[str] | None = None
) -> bool:
    """keep_terms un-junk default terms for a niche, e.g. "women's" for unisex sizing."""
    junk_re = _JUNK_RE
    if keep_terms:
        keep = {normalize_title(t) for t in keep_terms}
        junk_re = _terms_re([t for t in JUNK_TITLE_TERMS if normalize_title(t) not in keep])
    if junk_re.search(title):
        return True
    norm = normalize_title(title)
    return any(normalize_title(t) in norm for t in (extra_terms or []))


def remove_price_outliers(comps: list) -> list:
    if len(comps) < 8:
        return comps
    prices = sorted(c.price for c in comps)
    q1 = prices[len(prices) // 4]
    q3 = prices[3 * len(prices) // 4]
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return [c for c in comps if lower <= c.price <= upper]
