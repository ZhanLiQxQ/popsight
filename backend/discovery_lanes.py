from __future__ import annotations

from typing import Any, TypedDict


class DiscoveryLaneBlueprint(TypedDict):
    """One of six PoP retail lanes: stable id + UI label + Google Trends seed query."""

    category_id: str
    category_label: str
    trends_seed: str


# Six lanes: Node 0 uses `trends_seed` as the first Google Trends `q` (RELATED_QUERIES).
# Use search-volume-friendly phrases (how people type), not internal aisle slogans — niche
# marketing strings often chart as flat / empty in Trends. `category_label` stays the retail
# aisle for humans + MacroScout guardrails.
DISCOVERY_LANE_BLUEPRINTS: tuple[DiscoveryLaneBlueprint, ...] = (
    {"category_id": "asian_snacks", "category_label": "Asian Snacks", "trends_seed": "asian snacks"},
    {
        "category_id": "functional_beverages",
        "category_label": "Functional Beverages",
        "trends_seed": "energy drink",
    },
    {
        "category_id": "pantry_staples_asia",
        "category_label": "Pantry Staples Asia",
        "trends_seed": "asian groceries",
    },
    {
        "category_id": "instant_noodles_premium",
        "category_label": "Instant Noodles Premium",
        "trends_seed": "instant ramen",
    },
    {"category_id": "herbal_tea_drinks", "category_label": "Herbal Tea Drinks", "trends_seed": "herbal tea"},
    {
        "category_id": "better_for_you_candy",
        "category_label": "Better For You Candy",
        "trends_seed": "healthy candy",
    },
)

# Extra Trends `q` variants when the primary still returns no RELATED_QUERIES chart (deduped after primary).
TRENDS_QUERY_FALLBACKS_BY_CATEGORY_ID: dict[str, tuple[str, ...]] = {
    "asian_snacks": ("korean snacks", "japanese snacks", "rice crackers", "pocky", "mochi snack"),
    "functional_beverages": (
        "electrolyte drink",
        "functional drink",
        "kombucha",
        "vitamin water",
        "coconut water",
    ),
    "pantry_staples_asia": ("soy sauce", "gochujang", "fish sauce", "oyster sauce", "sesame oil"),
    "instant_noodles_premium": ("shin ramyun", "cup noodles", "ramen noodles", "premium instant noodles"),
    "herbal_tea_drinks": ("ginger tea", "matcha latte", "chai tea", "green tea drink"),
    "better_for_you_candy": ("low sugar candy", "protein gummies", "dark chocolate bar"),
}


def trend_query_variants(*, category_id: str, primary_seed: str) -> tuple[str, ...]:
    """Primary seed first, then deduped fallback queries for SerpAPI RELATED_QUERIES."""
    extras = TRENDS_QUERY_FALLBACKS_BY_CATEGORY_ID.get(category_id, ())
    primary = primary_seed.strip()
    seen: set[str] = set()
    out: list[str] = []
    for q in (primary, *extras):
        key = q.lower()
        if not q or key in seen:
            continue
        seen.add(key)
        out.append(q)
    return tuple(out)


def blueprints_for_lane_ids(ids: list[str] | None) -> tuple[DiscoveryLaneBlueprint, ...]:
    """
    Return the full six-lane tuple when ids is None or empty; otherwise lanes matching ids
    (preserving canonical DISCOVERY_LANE_BLUEPRINTS order).
    """
    if not ids:
        return DISCOVERY_LANE_BLUEPRINTS
    want = frozenset(ids)
    selected = tuple(bp for bp in DISCOVERY_LANE_BLUEPRINTS if bp["category_id"] in want)
    return selected if selected else DISCOVERY_LANE_BLUEPRINTS


def fresh_lane_state(bp: DiscoveryLaneBlueprint) -> dict[str, Any]:
    return {
        "category_id": bp["category_id"],
        "category_label": bp["category_label"],
        "trends_seed": bp["trends_seed"],
        "google_trends_signals": [],
        "amazon_search_terms": [],
        "raw_amazon_data": [],
        "compressed_items": [],
    }
