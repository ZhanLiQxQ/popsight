from __future__ import annotations

from typing import Any

import httpx

from .compressor import organic_dedupe_key, organic_review_count
from .macro_seeds import AMAZON_FOOD_BROWSE_NODE
from .serp_amazon import fetch_amazon_serp_json, organic_results


async def crawl_amazon_food_top_organics(
    *,
    amazon_search_terms: list[dict[str, Any]],
    api_key: str,
    amazon_domain: str = "amazon.com",
    browse_node: str = AMAZON_FOOD_BROWSE_NODE,
    max_organic_per_query: int = 48,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """
    For each MacroScout `{category, search_term}`, SerpAPI Amazon with `rh=n:<browse_node>`.
    Merge organics, sort by review count descending, dedupe by ASIN/URL, keep top `top_n`.
    """
    merged: list[dict[str, Any]] = []
    async with httpx.AsyncClient(headers={"User-Agent": "popsight-pipeline/1.0"}) as client:
        for row in amazon_search_terms:
            if not isinstance(row, dict):
                continue
            term = str(row.get("search_term") or "").strip()
            if not term:
                continue
            cat = str(row.get("category") or "").strip()
            payload = await fetch_amazon_serp_json(
                client,
                query=term,
                api_key=api_key,
                amazon_domain=amazon_domain,
                browse_node=browse_node,
            )
            if payload.get("error"):
                continue
            for raw in organic_results(payload)[:max(1, max_organic_per_query)]:
                if not isinstance(raw, dict):
                    continue
                annotated = dict(raw)
                annotated["macro_category"] = cat
                annotated["source_search_term"] = term
                merged.append(annotated)

    merged.sort(key=organic_review_count, reverse=True)
    seen: set[str] = set()
    top: list[dict[str, Any]] = []
    for raw in merged:
        key = organic_dedupe_key(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        top.append(raw)
        if len(top) >= top_n:
            break
    return top
