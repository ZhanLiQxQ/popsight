from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .amazon_categories import amazon_effective_rh_echo, resolve_amazon_browse_node
from .compressor import compress_amazon_organic_item
from .gliner_service import enrich_items_with_gliner
from .serp_amazon import fetch_amazon_serp_json, organic_results


async def run_amazon_compliance_pipeline(
    *,
    search_term: str,
    api_key: str,
    amazon_domain: str = "amazon.com",
    max_products: int = 40,
    include_raw_preview: bool = False,
    raw_preview_limit: int = 5,
    category_preset: str | None = None,
    category_node: str | None = None,
    gliner_enabled: bool = False,
    gliner_model_id: str = "urchade/gliner_small-v2.1",
    gliner_threshold: float = 0.35,
    gliner_max_input_chars: int = 1500,
    gliner_batch_size: int = 8,
    gliner_console_samples: int = 3,
) -> dict[str, Any]:
    """
    Fetch Amazon SERP via SerpAPI, then rule-filter + compress each organic result.
    Does not call any LLM.
    """
    amazon_browse_node = resolve_amazon_browse_node(
        category_preset=category_preset,
        category_node=category_node,
    )
    amazon_rh = amazon_effective_rh_echo(amazon_browse_node)
    amazon_category_preset: str | None = None
    if not (category_node or "").strip() and (category_preset or "").strip():
        amazon_category_preset = (category_preset or "").strip().lower()

    async with httpx.AsyncClient(headers={"User-Agent": "popsight-pipeline/1.0"}) as client:
        payload = await fetch_amazon_serp_json(
            client,
            query=search_term,
            api_key=api_key,
            amazon_domain=amazon_domain,
            browse_node=amazon_browse_node,
        )

    if payload.get("error"):
        return {
            "search_term": search_term,
            "amazon_domain": amazon_domain,
            "amazon_rh": amazon_rh,
            "amazon_browse_node": amazon_browse_node,
            "amazon_category_preset": amazon_category_preset,
            "raw_organic_count": 0,
            "dropped_compliance_count": 0,
            "items": [],
            "raw_preview": None,
            "serpapi_metadata": {
                "search_metadata": payload.get("search_metadata"),
                "error": payload.get("error"),
            },
            "serpapi_error": str(payload.get("error")),
        }

    rows = organic_results(payload)[: max(1, max_products)]
    items: list[dict[str, Any]] = []
    dropped = 0
    for raw in rows:
        compressed = compress_amazon_organic_item(raw)
        if compressed is None:
            dropped += 1
            continue
        items.append(compressed)

    if gliner_enabled and items:
        items = await asyncio.to_thread(
            enrich_items_with_gliner,
            items,
            model_id=gliner_model_id,
            threshold=gliner_threshold,
            max_input_chars=gliner_max_input_chars,
            batch_size=gliner_batch_size,
            console_samples=gliner_console_samples,
        )
    elif items:
        for it in items:
            it.setdefault("gliner_entities", [])
            it.setdefault("item_entities_compact", "")

    preview: list[dict[str, Any]] | None = None
    if include_raw_preview:
        preview = []
        for raw in rows[:raw_preview_limit]:
            preview.append(
                {
                    "title": raw.get("title"),
                    "price": raw.get("price"),
                    "link": raw.get("link") or raw.get("url"),
                }
            )

    return {
        "search_term": search_term,
        "amazon_domain": amazon_domain,
        "amazon_rh": amazon_rh,
        "amazon_browse_node": amazon_browse_node,
        "amazon_category_preset": amazon_category_preset,
        "raw_organic_count": len(rows),
        "dropped_compliance_count": dropped,
        "items": items,
        "raw_preview": preview,
        "serpapi_metadata": {
            "search_metadata": payload.get("search_metadata"),
            "error": payload.get("error"),
        },
        "serpapi_error": None,
    }
