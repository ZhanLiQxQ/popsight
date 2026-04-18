from __future__ import annotations

"""
Amazon US browse-node helpers for SerpAPI Amazon search.

Browse ids are sent to SerpAPI as **`rh=n:<id>`** with **`k`**, **`device=desktop`**, **`language=en_US`**
(see SerpAPI Amazon examples with filters). A bare **`node` + `k`** combo often returns HTTP 400.

Node IDs are **best-effort defaults** for amazon.com; Amazon can reorganize categories.
Override with `category_node` when you need a finer browse id (from the category URL `node=`).
"""

# preset api key -> browse node id (amazon.com)
AMAZON_CATEGORY_PRESETS: dict[str, str] = {
    # 1. Functional Health — Dietary Supplements (vitamins, minerals, herbals, etc.)
    "functional_health": "3764441",
    # 2. Beverages — Coffee, tea, bottled drinks subtree
    "beverages": "16310231",
    # 3. Snacks & Confectionery — packaged snack foods (chips, bars, etc.)
    #    Candy-heavy searches: override with category_node e.g. 16305641 (Candy & Chocolate; US site).
    "snacks_confectionery": "16317251",
    # 4. Grocery Staples — canned / jarred / packaged pantry-style foods (common US subtree)
    "grocery_staples": "6464939011",
    # 5. Personal Care & OTC — Health & Household (top-level; covers personal care + many OTC-style SKUs)
    "personal_care_otc": "3760901",
    # 6. Cultural / Specialty — International Food Market (Grocery; common US landing node)
    "cultural_specialty": "17428419011",
}

# Human-readable labels (for docs / optional UI); keys match `category_preset`.
AMAZON_CATEGORY_LABELS: dict[str, tuple[str, str]] = {
    "functional_health": ("Functional Health", "Supplements & herbal SKUs"),
    "beverages": ("Beverages", "Bottled drinks & tea"),
    "snacks_confectionery": ("Snacks & Confectionery", "Packaged snacks & candy"),
    "grocery_staples": ("Grocery Staples", "Pantry & packaged foods"),
    "personal_care_otc": ("Personal Care & OTC", "Household & OTC-style items"),
    "cultural_specialty": ("Cultural / Specialty Products", "International / specialty grocery"),
}

# Older API preset names → same browse nodes (backward compatible).
_LEGACY_PRESET_NODES: dict[str, str] = {
    "grocery": "16310101",
    "snacks": "16317251",
    "supplements": "3764441",
}


def resolve_amazon_browse_node(
    *,
    category_preset: str | None,
    category_node: str | None,
) -> str | None:
    """
    Resolve Amazon browse node id for SerpAPI's `node` parameter.

    - If `category_node` is set (non-empty digits), it wins.
    - Else if `category_preset` maps to a known preset (or legacy alias), use that node.
    - Else return None for a global Amazon search (no category lock).
    """
    raw_node = (category_node or "").strip()
    if raw_node:
        if raw_node.lower().startswith("n:"):
            raw_node = raw_node.split(":", 1)[-1].strip()
        return raw_node

    key = (category_preset or "").strip().lower()
    if not key or key in {"none", "any", "all"}:
        return None

    return AMAZON_CATEGORY_PRESETS.get(key) or _LEGACY_PRESET_NODES.get(key)


def amazon_effective_rh_echo(node: str | None) -> str | None:
    """Informational `n:<id>` string for API responses (Amazon URL style); not sent to SerpAPI as `rh`."""
    if not node:
        return None
    return f"n:{node}"
