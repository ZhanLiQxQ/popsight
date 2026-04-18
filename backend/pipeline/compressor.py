from __future__ import annotations

import re
from typing import Any

from .compliance import fda_compliance_violation
from .extractive import (
    build_review_summary_and_evidence,
    collect_detail_corpus_lines,
    extractive_detail,
    gather_review_evidence_snippets,
)

_ASIN_RE = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?]|$)", re.I)
_PRICE_RE = re.compile(r"[\d,.]+")
_BOUGHT_RE = re.compile(
    r"([\d,.]+)\s*([kmb])?\s*\+?\s*bought",
    re.I,
)
_INT_RE = re.compile(r"[\d,]+")


def _clean_text(s: str | None) -> str:
    if not s:
        return ""
    t = re.sub(r"<[^>]+>", " ", str(s))
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _parse_price(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        d = raw
        raw = d.get("value")
        if raw is None:
            raw = d.get("extracted_value")
        if raw is None:
            raw = d.get("raw")
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw)
    m = _PRICE_RE.search(s.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _parse_rating(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    m = re.search(r"(\d+(?:\.\d+)?)", str(raw))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _parse_int_loose(raw: Any) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    s = str(raw).lower().replace(",", "")
    m = re.search(r"([\d.]+)\s*([kmb])?", s)
    if not m:
        digits = _INT_RE.search(s)
        if not digits:
            return None
        return int(digits.group(0).replace(",", ""))
    n = float(m.group(1))
    suf = (m.group(2) or "").lower()
    if suf == "k":
        n *= 1_000
    elif suf == "m":
        n *= 1_000_000
    elif suf == "b":
        n *= 1_000_000_000
    return int(round(n))


def _extract_asin(link: str | None) -> str | None:
    if not link:
        return None
    m = _ASIN_RE.search(link)
    return m.group(1).upper() if m else None


def _extract_bought_past_month(text: str) -> int | None:
    m = _BOUGHT_RE.search(text.lower())
    if not m:
        return None
    return _parse_int_loose(m.group(0))


def compress_amazon_organic_item(raw: dict[str, Any]) -> dict[str, Any] | None:
    """
    Map a SerpAPI organic_result-ish dict to the compressed schema, or None if dropped.
    """
    title = _clean_text(raw.get("title"))
    snippet = _clean_text(raw.get("snippet"))
    link = raw.get("link") or raw.get("url")
    link_s = str(link) if link else None

    price = _parse_price(raw.get("price") or raw.get("extracted_price"))
    rating = _parse_rating(raw.get("rating"))
    reviews = _parse_int_loose(raw.get("reviews") or raw.get("reviews_count") or raw.get("ratings_total"))

    extensions: dict[str, Any] = {}
    if isinstance(raw.get("extensions"), dict):
        extensions["extensions"] = raw["extensions"]
    if isinstance(raw.get("extensions_flat"), list):
        extensions["extensions_flat"] = raw["extensions_flat"]
    if isinstance(raw.get("feature_bullets"), list):
        extensions["feature_bullets"] = raw["feature_bullets"]

    violation = fda_compliance_violation(title, snippet, raw.get("description"))
    if violation:
        return None

    corpus = collect_detail_corpus_lines(title=title, snippet=snippet, extensions=extensions, raw=raw)
    detail = extractive_detail(title, corpus, max_chars=720)
    violation2 = fda_compliance_violation(detail)
    if violation2:
        return None

    evidence_snips = gather_review_evidence_snippets(raw, snippet)
    review_summary, review_evidence, review_source = build_review_summary_and_evidence(
        evidence_snips,
        rating=rating,
        review_count=reviews,
    )

    bought = _extract_bought_past_month(f"{title} {snippet}")
    sold_proxy = bought if bought is not None else reviews

    return {
        "item_name": title[:240] or "Unknown item",
        "item_detail": detail,
        "item_reviews_summarized": review_summary,
        "item_review_evidence": review_evidence,
        "item_review_source": review_source,
        "item_price": price,
        "item_sold_quantity": sold_proxy,
        "item_rating": rating,
        "item_review_count": reviews,
        "source_url": link_s,
        "asin": _extract_asin(link_s),
    }


def organic_review_count(raw: dict[str, Any]) -> int:
    """SerpAPI Amazon organic: best-effort review count for sorting."""
    v = _parse_int_loose(raw.get("reviews") or raw.get("reviews_count") or raw.get("ratings_total"))
    return int(v) if v is not None else 0


def organic_dedupe_key(raw: dict[str, Any]) -> str:
    link = raw.get("link") or raw.get("url")
    link_s = str(link) if link else ""
    asin = _extract_asin(link_s)
    if asin:
        return f"asin:{asin}"
    title = _clean_text(raw.get("title"))[:120]
    return f"url:{link_s}|t:{title}"
