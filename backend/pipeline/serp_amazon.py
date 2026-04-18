from __future__ import annotations

import httpx

SERPAPI_SEARCH_URL = "https://serpapi.com/search"


async def fetch_amazon_serp_json(
    client: httpx.AsyncClient,
    *,
    query: str,
    api_key: str,
    amazon_domain: str = "amazon.com",
    browse_node: str | None = None,
) -> dict:
    """
    Async SerpAPI Amazon search.

    Uses `k` (query). Category lock uses **`rh=n:<browse_node>`** plus `device` + `language`,
    matching SerpAPI docs (filtered examples use `rh`, not a bare `node` + `k` combo, which
    can return HTTP 400).
    See https://serpapi.com/amazon-search-api
    """
    params: dict[str, str] = {
        "engine": "amazon",
        "amazon_domain": amazon_domain,
        "device": "desktop",
        "language": "en_US",
        "k": query,
        "api_key": api_key,
    }
    if browse_node:
        params["rh"] = f"n:{browse_node}"
    response = await client.get(SERPAPI_SEARCH_URL, params=params, timeout=60.0)
    response.raise_for_status()
    return response.json()


def organic_results(payload: dict) -> list[dict]:
    return list(payload.get("organic_results") or [])
