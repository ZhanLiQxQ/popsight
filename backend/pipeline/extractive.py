"""
Extractive text packing for Amazon organic rows (no LLM).

Goals:
- Prefer information-dense, non-redundant sentences within a char budget.
- Review fields are limited by SerpAPI search organic data (usually no full review bodies).
"""

from __future__ import annotations

import re
from typing import Any

# Light stopwords for overlap scoring (not linguistic parsing)
_STOP = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "your",
        "pack",
        "count",
        "ounce",
        "ounces",
        "fl",
        "oz",
        "ml",
        "per",
        "are",
        "you",
        "our",
        "its",
    },
)


def _clean(s: str | None) -> str:
    if not s:
        return ""
    t = re.sub(r"<[^>]+>", " ", str(s))
    return re.sub(r"\s+", " ", t).strip()


def _title_tokens(title: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", title.lower()) if t not in _STOP}


def _split_clauses(text: str) -> list[str]:
    if not text:
        return []
    chunks = re.split(r"\s*·\s*|\s*\|\s*|\s*;\s+", text)
    out: list[str] = []
    for ch in chunks:
        ch = ch.strip()
        if not ch:
            continue
        subs = re.split(r"(?<=[.!?])\s+", ch)
        for s in subs:
            s = s.strip()
            if len(s) >= 14:
                out.append(s)
    return out


def _fingerprint(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower())[:120]


def _dedupe_preserve_order(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        fp = _fingerprint(line)
        if fp in seen:
            continue
        seen.add(fp)
        out.append(line)
    return out


def _score_detail_sentence(sentence: str, title_tokens: set[str]) -> float:
    sl = sentence.lower()
    words = set(re.findall(r"[a-z0-9]{3,}", sl))
    score = 0.0
    overlap = words & title_tokens
    score += 1.4 * (len(overlap) ** 0.5)
    if any(c.isdigit() for c in sentence):
        score += 1.6
    ln = len(sentence)
    if 36 <= ln <= 200:
        score += 1.1
    elif ln > 260:
        score -= 0.8
    if sl.count(",") >= 3:
        score += 0.35
    return score


def collect_detail_corpus_lines(
    *,
    title: str,
    snippet: str,
    extensions: dict[str, Any],
    raw: dict[str, Any],
) -> list[str]:
    """Flatten every useful organic field into short lines for extractive packing."""
    lines: list[str] = []

    sn = _clean(snippet)
    if sn:
        lines.append(sn)

    desc = _clean(raw.get("description"))
    if desc:
        lines.append(desc)

    if isinstance(raw.get("feature_bullets"), list):
        lines.extend(_clean(str(x)) for x in raw["feature_bullets"] if x)

    flat = extensions.get("extensions_flat")
    if isinstance(flat, list):
        lines.extend(_clean(str(x)) for x in flat if x)

    ext = extensions.get("extensions") if isinstance(extensions.get("extensions"), dict) else {}
    if isinstance(ext, dict):
        for k, v in list(ext.items())[:12]:
            if isinstance(v, list):
                lines.extend(_clean(str(x)) for x in v[:4] if x)
            else:
                lines.append(_clean(f"{k}: {v}"))

    specs = raw.get("specs")
    if isinstance(specs, dict):
        for k, v in list(specs.items())[:16]:
            lines.append(_clean(f"{k}: {v}"))

    brand = _clean(raw.get("brand"))
    if brand:
        lines.append(f"Brand: {brand}")

    blm = _clean(raw.get("bought_last_month"))
    if blm:
        lines.append(f"Purchase signal: {blm}")

    for key in ("offers", "delivery"):
        val = raw.get(key)
        if isinstance(val, list):
            lines.extend(_clean(str(x)) for x in val[:4] if x)
        elif isinstance(val, str) and val.strip():
            lines.append(_clean(val))

    tags = raw.get("tags")
    if isinstance(tags, list):
        lines.append("Tags: " + ", ".join(_clean(str(t)) for t in tags[:8] if t))

    sus = raw.get("sustainability_features")
    if isinstance(sus, list):
        for row in sus[:4]:
            if isinstance(row, dict):
                nm = _clean(row.get("name"))
                snp = _clean(row.get("snippet"))
                if nm or snp:
                    lines.append(_clean(f"{nm}: {snp}".strip(": ")))

    return _dedupe_preserve_order([x for x in lines if x])


def extractive_detail(title: str, corpus_lines: list[str], max_chars: int = 720) -> str:
    title_c = _clean(title)[:220] or "Item"
    tt = _title_tokens(title_c)

    candidates: list[str] = []
    for line in corpus_lines:
        for sent in _split_clauses(line):
            tl = sent.lower()
            if len(sent) < 16:
                continue
            if tl == title_c.lower()[: len(tl)]:
                continue
            candidates.append(sent)

    candidates = _dedupe_preserve_order(candidates)
    candidates.sort(key=lambda s: _score_detail_sentence(s, tt), reverse=True)

    parts: list[str] = [title_c]
    used = len(title_c)
    sep = " · "
    for s in candidates:
        if used >= max_chars - 24:
            break
        chunk = s if len(s) <= 280 else s[:277] + "…"
        extra = sep + chunk
        if used + len(extra) > max_chars:
            room = max_chars - used - len(sep)
            if room < 24:
                break
            chunk = s[: max(0, room - 1)] + "…"
            extra = sep + chunk
        parts.append(chunk)
        used += len(extra)

    return parts[0] if len(parts) == 1 else parts[0] + sep + sep.join(parts[1:])


def gather_review_evidence_snippets(raw: dict[str, Any], snippet: str) -> list[str]:
    """Collect short customer-facing lines available on the search SERP (not PDP review bodies)."""
    out: list[str] = []
    sn = _clean(snippet)
    if sn:
        for clause in re.split(r"\s*·\s*|\s*\|\s*", sn):
            c = clause.strip()
            if len(c) > 24:
                out.append(c)
        if not out and len(sn) > 12:
            out.append(sn)
    for key in ("snippet_highlighted", "highlights", "customers_say"):
        val = raw.get(key)
        if isinstance(val, str) and len(val.strip()) > 24:
            out.append(_clean(val))
        elif isinstance(val, list):
            for x in val[:4]:
                t = _clean(str(x))
                if len(t) > 24:
                    out.append(t)
    return _dedupe_preserve_order(out)[:8]


_POS = frozenset(
    {
        "great",
        "good",
        "love",
        "perfect",
        "excellent",
        "amazing",
        "best",
        "nice",
        "fresh",
        "delicious",
        "refreshing",
        "smooth",
        "quality",
        "recommend",
        "happy",
        "awesome",
        "tasty",
    }
)
_NEG = frozenset(
    {
        "bad",
        "awful",
        "terrible",
        "waste",
        "returned",
        "disappointed",
        "poor",
        "cheap",
        "broken",
        "fake",
        "stale",
        "gross",
        "nasty",
        "horrible",
    }
)


def _review_sentence_score(sentence: str) -> float:
    tok = re.findall(r"[a-z]{3,}", sentence.lower())
    pos = sum(1 for t in tok if t in _POS)
    neg = sum(1 for t in tok if t in _NEG)
    return (pos - neg) * 2.2 + (len(sentence) ** 0.35)


def build_review_summary_and_evidence(
    evidence_snippets: list[str],
    *,
    rating: float | None,
    review_count: int | None,
    summary_max_chars: int = 420,
    evidence_chunk_max: int = 240,
    evidence_max_chunks: int = 5,
) -> tuple[str, list[str], str]:
    """
    Returns (summary, evidence_chunks, source_label).

    ``source_label`` explains that full customer reviews are not available from search organic alone.
    """
    source = "amazon_search_serp_snippets"

    trimmed_evidence: list[str] = []
    for e in evidence_snippets:
        e = e.strip()
        if not e:
            continue
        if len(e) > evidence_chunk_max:
            e = e[: evidence_chunk_max - 1] + "…"
        trimmed_evidence.append(e)
        if len(trimmed_evidence) >= evidence_max_chunks:
            break

    sentences: list[str] = []
    for e in evidence_snippets:
        sentences.extend(_split_clauses(e))
    sentences = [s for s in _dedupe_preserve_order(sentences) if len(s) >= 18]
    sentences.sort(key=_review_sentence_score, reverse=True)

    meta_parts: list[str] = []
    if rating is not None:
        meta_parts.append(f"Listing avg {rating:.1f}★")
    if review_count is not None:
        meta_parts.append(f"{review_count} ratings on card")
    meta_parts.append("evidence=search snippets not full reviews")

    body: list[str] = []
    budget = summary_max_chars - len("; ".join(meta_parts)) - 8
    for s in sentences:
        if budget < 28:
            break
        chunk = s if len(s) <= budget else s[: max(0, budget - 1)] + "…"
        body.append(chunk)
        budget -= len(chunk) + 2
        if len(body) >= 4:
            break

    summary = "; ".join(meta_parts + body) if body else "; ".join(meta_parts)
    if len(summary) > summary_max_chars:
        summary = summary[: summary_max_chars - 1] + "…"

    return summary, trimmed_evidence, source

