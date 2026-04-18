from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ChatMessagePayload(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime
    productIds: list[str] | None = None


class ConversationPayload(BaseModel):
    id: str
    title: str
    topic: str
    scanSessionId: str | None = None
    createdAt: datetime
    updatedAt: datetime
    messages: list[ChatMessagePayload]


class MemoryPayload(BaseModel):
    id: str
    kind: Literal["user_preference", "product_insight", "supplier_note", "decision"]
    title: str
    content: str
    sourceConversationId: str | None = None
    sourceScanSessionId: str | None = None
    createdAt: datetime
    updatedAt: datetime
    pinned: bool = False


class TrendPayload(BaseModel):
    id: str
    topic: str
    category: str
    growth: str
    sentiment: Literal["Positive", "Neutral", "Mixed"] = "Neutral"
    topKeywords: list[str] = Field(default_factory=list)


class ProductPayload(BaseModel):
    id: str
    name: str
    brand: str
    category: str
    origin: str
    tractionScore: int
    velocity: Literal["Rising", "Explosive", "Stable"] = "Stable"
    distributionStatus: Literal["Parallel Import", "Under-distributed", "Not in US"] = (
        "Under-distributed"
    )
    pricePoint: str
    description: str
    image: str | None = None


class ManufacturerPayload(BaseModel):
    id: str
    name: str
    location: str
    specialization: list[str] = Field(default_factory=list)
    capacity: Literal["Low", "Medium", "High"] = "Medium"
    contactStatus: Literal["Identified", "Contacted", "Partner"] = "Identified"


class ScanSessionPayload(BaseModel):
    id: str
    topic: str
    createdAt: datetime
    trends: list[TrendPayload]
    opportunities: list[ProductPayload]
    manufacturers: list[ManufacturerPayload]
    summary: str


class AgentLogPayload(BaseModel):
    id: str
    agentName: str
    message: str
    timestamp: datetime
    type: Literal["info", "success", "warning", "error"] = "info"


class MacroSuggestionPayload(BaseModel):
    category: str
    reason: str
    region: str
    growthIndicator: str


class GlinerEntityPayload(BaseModel):
    text: str
    label: str
    score: float = 0.0


class CompressedAmazonItem(BaseModel):
    """Token-efficient product row after crawl + rule/NLP compression."""

    item_name: str
    item_detail: str
    item_reviews_summarized: str
    item_review_evidence: list[str] = Field(
        default_factory=list,
        description="Short SERP-side snippets used for review signal (not full PDP reviews).",
    )
    item_review_source: str = Field(
        default="amazon_search_serp_snippets",
        description="Where review-ish text came from; full bodies need amazon_product scrape or similar.",
    )
    item_price: float | None = None
    item_sold_quantity: int | None = None
    item_rating: float | None = None
    item_review_count: int | None = None
    source_url: str | None = None
    asin: str | None = None
    gliner_entities: list[GlinerEntityPayload] = Field(default_factory=list)
    item_entities_compact: str = ""


class AmazonSerpMetadata(BaseModel):
    search_metadata: dict[str, Any] | None = None
    error: str | None = None


AmazonCategoryPreset = Literal[
    "functional_health",
    "beverages",
    "snacks_confectionery",
    "grocery_staples",
    "personal_care_otc",
    "cultural_specialty",
    "grocery",
    "snacks",
    "supplements",
]


class AmazonPipelineRequest(BaseModel):
    """Macro trend / category style query, e.g. \"Korean zero sugar soda\"."""

    query: str = Field(min_length=1, max_length=400)
    userId: str = "default-user"
    max_products: int = Field(default=40, ge=1, le=60)
    amazon_domain: str = "amazon.com"
    include_raw_preview: bool = False
    category_preset: AmazonCategoryPreset | None = Field(
        default=None,
        description=(
            "Six macro aisles (amazon.com browse nodes; see backend/pipeline/amazon_categories.py): "
            "functional_health (supplements/herbals subtree), beverages, snacks_confectionery, grocery_staples, "
            "personal_care_otc, cultural_specialty. Legacy: grocery, snacks, supplements."
        ),
    )
    category_node: str | None = Field(
        default=None,
        max_length=32,
        description=(
            "Amazon browse node id (digits only), e.g. 16310101. Overrides category_preset. "
            "Leave empty / omit in Swagger — do not submit the example word 'string'."
        ),
    )

    @field_validator("category_node", mode="before")
    @classmethod
    def normalize_category_node(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return None
        s = value.strip()
        if not s:
            return None
        if s.lower() in {"string", "null", "none", "undefined", "example"}:
            return None
        if s.lower().startswith("n:"):
            s = s.split(":", 1)[-1].strip()
        if not s.isdigit():
            raise ValueError(
                "category_node must be digits only (Amazon browse node id), e.g. 16310101. "
                "Remove the field to use category_preset only."
            )
        return s


class DiscoveryLaneId(str, Enum):
    """Six PoP discovery retail lanes — only these values are accepted in `discoveryLaneIds`."""

    asian_snacks = "asian_snacks"
    functional_beverages = "functional_beverages"
    pantry_staples_asia = "pantry_staples_asia"
    instant_noodles_premium = "instant_noodles_premium"
    herbal_tea_drinks = "herbal_tea_drinks"
    better_for_you_candy = "better_for_you_candy"


class MacroColdStartRequest(BaseModel):
    """Phase 1–2 cold start: Google Trends seeds → MacroScout → Amazon (Grocery node) → compression."""

    userId: str = "default-user"
    googleTrendsGeo: str = Field(default="US", max_length=16, description="SerpAPI Google Trends `geo` (e.g. US).")
    amazonDomain: str = Field(default="amazon.com", max_length=64)
    discoveryLaneIds: list[DiscoveryLaneId] | None = Field(
        default=None,
        max_length=6,
        description=(
            "Subset of discovery lanes to run (Swagger: enum only). Omit or null to run all six lanes "
            "in canonical order."
        ),
    )


MACRO_COLD_START_OPENAPI_EXAMPLES: dict[str, dict[str, Any]] = {
    "all_six_lanes": {
        "summary": "All six lanes (default)",
        "description": "Runs every `DiscoveryLaneId` lane; highest SerpAPI usage.",
        "value": {
            "userId": "default-user",
            "googleTrendsGeo": "US",
            "amazonDomain": "amazon.com",
        },
    },
    "lane_asian_snacks": {
        "summary": "Lane: asian_snacks",
        "value": {
            "userId": "default-user",
            "googleTrendsGeo": "US",
            "amazonDomain": "amazon.com",
            "discoveryLaneIds": [DiscoveryLaneId.asian_snacks.value],
        },
    },
    "lane_functional_beverages": {
        "summary": "Lane: functional_beverages",
        "value": {
            "userId": "default-user",
            "googleTrendsGeo": "US",
            "amazonDomain": "amazon.com",
            "discoveryLaneIds": [DiscoveryLaneId.functional_beverages.value],
        },
    },
    "lane_pantry_staples_asia": {
        "summary": "Lane: pantry_staples_asia",
        "value": {
            "userId": "default-user",
            "googleTrendsGeo": "US",
            "amazonDomain": "amazon.com",
            "discoveryLaneIds": [DiscoveryLaneId.pantry_staples_asia.value],
        },
    },
    "lane_instant_noodles_premium": {
        "summary": "Lane: instant_noodles_premium",
        "value": {
            "userId": "default-user",
            "googleTrendsGeo": "US",
            "amazonDomain": "amazon.com",
            "discoveryLaneIds": [DiscoveryLaneId.instant_noodles_premium.value],
        },
    },
    "lane_herbal_tea_drinks": {
        "summary": "Lane: herbal_tea_drinks",
        "value": {
            "userId": "default-user",
            "googleTrendsGeo": "US",
            "amazonDomain": "amazon.com",
            "discoveryLaneIds": [DiscoveryLaneId.herbal_tea_drinks.value],
        },
    },
    "lane_better_for_you_candy": {
        "summary": "Lane: better_for_you_candy",
        "value": {
            "userId": "default-user",
            "googleTrendsGeo": "US",
            "amazonDomain": "amazon.com",
            "discoveryLaneIds": [DiscoveryLaneId.better_for_you_candy.value],
        },
    },
    "two_lanes_snacks_beverages": {
        "summary": "Two lanes (enum subset)",
        "value": {
            "userId": "default-user",
            "googleTrendsGeo": "US",
            "amazonDomain": "amazon.com",
            "discoveryLaneIds": [
                DiscoveryLaneId.asian_snacks.value,
                DiscoveryLaneId.functional_beverages.value,
            ],
        },
    },
    "all_six_explicit_enums": {
        "summary": "All six lanes (explicit discoveryLaneIds only)",
        "description": "Same as default run but every lane id is an enum string in the body.",
        "value": {
            "userId": "default-user",
            "googleTrendsGeo": "US",
            "amazonDomain": "amazon.com",
            "discoveryLaneIds": [
                DiscoveryLaneId.asian_snacks.value,
                DiscoveryLaneId.functional_beverages.value,
                DiscoveryLaneId.pantry_staples_asia.value,
                DiscoveryLaneId.instant_noodles_premium.value,
                DiscoveryLaneId.herbal_tea_drinks.value,
                DiscoveryLaneId.better_for_you_candy.value,
            ],
        },
    },
}


class DiscoveryLaneResult(BaseModel):
    """One of six PoP retail lanes: full Node 0–3 artifacts."""

    categoryId: str
    categoryLabel: str
    trendsSeed: str
    googleTrendsSignals: list[dict[str, Any]] = Field(default_factory=list)
    amazonSearchTerms: list[dict[str, str]] = Field(default_factory=list)
    rawAmazonData: list[dict[str, Any]] = Field(default_factory=list)
    compressedItems: list[CompressedAmazonItem] = Field(default_factory=list)


class MacroColdStartResponse(BaseModel):
    lanes: list[DiscoveryLaneResult] = Field(
        default_factory=list,
        description="Six retail aisles; each lane has its own trends → MacroScout → Amazon Top-5 → compressed items.",
    )
    googleTrendsSignals: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Aggregate of all lane signals (same order as lanes concatenated).",
    )
    amazonSearchTerms: list[dict[str, str]] = Field(
        default_factory=list,
        description="Aggregate MacroScout rows across all lanes.",
    )
    rawAmazonData: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Aggregate raw Amazon organics across lanes.",
    )
    compressedItems: list[CompressedAmazonItem] = Field(
        default_factory=list,
        description="Aggregate compressed rows across lanes (flat convenience).",
    )
    rankedProductList: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Node 4 ranked products (Trend Analyst).",
    )
    finalActionableList: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Node 5 supply / action rows.",
    )
    executiveSummary: str = Field(
        default="",
        description="Node 6 Markdown executive summary.",
    )
    discoveryAborted: bool = Field(
        default=False,
        description="True when Node 0 produced no usable rising queries for any lane; later nodes were skipped.",
    )
    discoveryAbortReason: str | None = Field(
        default=None,
        description="Human-readable reason when discoveryAborted is true.",
    )


class AmazonPipelineResponse(BaseModel):
    search_term: str
    amazon_domain: str
    amazon_rh: str | None = Field(
        default=None,
        description="Category filter sent to SerpAPI as `rh` (e.g. n:16310231) alongside `k`, device, language.",
    )
    amazon_browse_node: str | None = None
    amazon_category_preset: str | None = None
    raw_organic_count: int
    dropped_compliance_count: int
    items: list[CompressedAmazonItem]
    raw_preview: list[dict[str, Any]] | None = None
    serpapi_metadata: AmazonSerpMetadata | None = None


class BootstrapResponse(BaseModel):
    conversations: list[ConversationPayload]
    memories: list[MemoryPayload]
    scanSessions: list[ScanSessionPayload]
    agentLogs: list[AgentLogPayload]
    macros: list[MacroSuggestionPayload]


class ScanRequest(BaseModel):
    topic: str
    userId: str = "default-user"


class ScanResponse(BaseModel):
    conversation: ConversationPayload
    scanSession: ScanSessionPayload
    agentLogs: list[AgentLogPayload]


class ChatRequest(BaseModel):
    conversationId: str | None = None
    scanSessionId: str | None = None
    userId: str = "default-user"
    message: str
    selectedProductId: str | None = None
    selectedTrendId: str | None = None
    selectedManufacturerId: str | None = None


class ChatResponse(BaseModel):
    conversation: ConversationPayload
    memories: list[MemoryPayload]
    agentLogs: list[AgentLogPayload]


class SaveMemoryRequest(BaseModel):
    userId: str = "default-user"
    conversationId: str | None = None
    scanSessionId: str | None = None
    kind: Literal["user_preference", "product_insight", "supplier_note", "decision"]
    title: str
    content: str


class SaveMemoryResponse(BaseModel):
    memory: MemoryPayload
    memories: list[MemoryPayload]
