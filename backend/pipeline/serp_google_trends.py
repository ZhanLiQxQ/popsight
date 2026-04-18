from __future__ import annotations

from typing import Any, Literal

import httpx

from .macro_seeds import GOOGLE_TRENDS_SEED_TERMS

SERPAPI_SEARCH_URL = "https://serpapi.com/search"


async def fetch_google_trends_related_queries_rising(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    seed_term: str,
    geo: str = "US",
    hl: str = "en",
    date: str = "today 12-m",
    tz: str = "420",
    include_low_search_volume: bool = True,
) -> dict[str, Any]:
    """
    SerpAPI Google Trends RELATED_QUERIES chart (single `q` per request).
    Response includes `related_queries.rising` with query, value, extracted_value.
    """
    params: dict[str, str] = {
        "engine": "google_trends",
        "q": seed_term,
        "data_type": "RELATED_QUERIES",
        "api_key": api_key,
        "date": date,
        "tz": tz,
        "hl": hl,
    }
    if geo:
        params["geo"] = geo
    if include_low_search_volume:
        params["include_low_search_volume"] = "true"
    response = await client.get(SERPAPI_SEARCH_URL, params=params, timeout=60.0)
    response.raise_for_status()
    return response.json()


def flatten_related_queries_signals(
    *,
    seed_term: str,
    payload: dict[str, Any],
    bucket: Literal["rising", "top"],
    max_rows: int = 25,
) -> list[dict[str, Any]]:
    """
    Normalize SerpAPI `related_queries.rising` or `.top` into rows for `google_trends_signals`.

    Google often returns an empty `rising` slice while `top` still has queries; using `top` is a
    weaker signal than rising but avoids a dead Node 0 without an extra SerpAPI request.
    """
    if payload.get("error"):
        return []
    raw = (payload.get("related_queries") or {}).get(bucket) or []
    out: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for row in raw[:max_rows]:
        if not isinstance(row, dict):
            continue
        q = str(row.get("query") or "").strip()
        if not q:
            continue
        out.append(
            {
                "seed_category": seed_term,
                "query": q,
                "growth": str(row.get("value") or "").strip(),
                "growth_extracted": row.get("extracted_value"),
                "trends_signal_bucket": bucket,
            }
        )
    return out


def flatten_rising_signals(
    *,
    seed_term: str,
    payload: dict[str, Any],
    max_rising_per_seed: int = 25,
) -> list[dict[str, Any]]:
    """Normalize SerpAPI `related_queries.rising` into rows for `google_trends_signals`."""
    return flatten_related_queries_signals(
        seed_term=seed_term,
        payload=payload,
        bucket="rising",
        max_rows=max_rising_per_seed,
    )


async def fetch_related_queries_rising_with_query_fallbacks(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    query_variants: tuple[str, ...],
    geo: str,
    signal_seed_label: str,
    include_low_search_volume: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Try RELATED_QUERIES `q` variants until `rising` is non-empty (Google often has no chart for long marketing phrases).

    Each returned row uses `seed_category=signal_seed_label` (stable lane label) and adds `trends_query_used`
    with the SerpAPI `q` that produced the row.
    """
    last_error: str | None = None
    tried: list[str] = []
    for q in query_variants:
        qt = q.strip()
        if not qt:
            continue
        tried.append(qt)
        try:
            payload = await fetch_google_trends_related_queries_rising(
                client,
                api_key=api_key,
                seed_term=qt,
                geo=geo,
                include_low_search_volume=include_low_search_volume,
            )
        except Exception as e:
            last_error = str(e)[:400]
            continue
        if payload.get("error"):
            last_error = str(payload.get("error"))[:400]
            rows = []
        else:
            rows = flatten_related_queries_signals(
                seed_term=signal_seed_label, payload=payload, bucket="rising", max_rows=25
            )
            if not rows:
                rows = flatten_related_queries_signals(
                    seed_term=signal_seed_label, payload=payload, bucket="top", max_rows=15
                )
        if not rows and not (payload.get("error")):
            last_error = "RELATED_QUERIES rising and top were both empty for this q."
        if rows:
            for row in rows:
                row["trends_query_used"] = qt
            return rows, {"winning_trends_query": qt, "attempts": tried, "error": None}
    err = last_error or "Google Trends returned no rising RELATED_QUERIES for any variant."
    return (
        [
            {
                "seed_category": signal_seed_label,
                "query": "",
                "growth": "",
                "growth_extracted": None,
                "error": err,
                "trends_variants_tried": tried,
            }
        ],
        {"winning_trends_query": None, "attempts": tried, "error": err},
    )


async def collect_default_seed_rising_signals(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    seeds: tuple[str, ...] | None = None,
    geo: str = "US",
) -> list[dict[str, Any]]:
    """Fetch RELATED_QUERIES rising for each default seed; returns a flat list."""
    seeds = seeds or GOOGLE_TRENDS_SEED_TERMS
    combined: list[dict[str, Any]] = []
    for seed in seeds:
        try:
            payload = await fetch_google_trends_related_queries_rising(
                client, api_key=api_key, seed_term=seed, geo=geo
            )
        except Exception as e:
            combined.append(
                {
                    "seed_category": seed,
                    "query": "",
                    "growth": "",
                    "growth_extracted": None,
                    "error": str(e)[:240],
                }
            )
            continue
        rows = flatten_rising_signals(seed_term=seed, payload=payload)
        if not rows and payload.get("error"):
            combined.append(
                {
                    "seed_category": seed,
                    "query": "",
                    "growth": "",
                    "growth_extracted": None,
                    "error": str(payload.get("error"))[:240],
                }
            )
        else:
            combined.extend(rows)
    return combined
