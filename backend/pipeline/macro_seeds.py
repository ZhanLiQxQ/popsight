from __future__ import annotations

"""Google Trends seeds — aligned with `backend.discovery_lanes.DISCOVERY_LANE_BLUEPRINTS`."""

from ..discovery_lanes import DISCOVERY_LANE_BLUEPRINTS

GOOGLE_TRENDS_SEED_TERMS: tuple[str, ...] = tuple(bp["trends_seed"] for bp in DISCOVERY_LANE_BLUEPRINTS)

# Amazon Grocery & Gourmet Food browse node (US); macro cold-start crawler locks to this node.
AMAZON_FOOD_BROWSE_NODE: str = "16310101"
