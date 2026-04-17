from __future__ import annotations

import json
import re
from typing import Any
import hashlib

from google import genai
from google.genai import types as google_types
from langchain_google_genai import ChatGoogleGenerativeAI

from .config import settings
from .schemas import MacroSuggestionPayload


class LLMService:
    def __init__(self) -> None:
        self.client = None
        self.chat_model = None
        self.demo_mode = False

    def ensure_clients(self) -> None:
        if not settings.gemini_api_key:
            if settings.allow_demo_mode_without_llm_key and settings.app_env != "production":
                self.demo_mode = True
                return
            raise ValueError("Missing GEMINI_API_KEY or GOOGLE_API_KEY.")

        if self.client is None:
            self.client = genai.Client(api_key=settings.gemini_api_key)

        if self.chat_model is None:
            self.chat_model = ChatGoogleGenerativeAI(
                model=settings.chat_model,
                google_api_key=settings.gemini_api_key,
                temperature=0.2,
            )

    async def get_macro_discoveries(self) -> list[MacroSuggestionPayload]:
        self.ensure_clients()
        if self.demo_mode:
            return [
                MacroSuggestionPayload(
                    category="Demo: Asia-forward snacks",
                    reason="Demo mode (no LLM key). Replace with real Gemini key to get grounded results.",
                    region="Asia",
                    growthIndicator="Rising",
                ),
                MacroSuggestionPayload(
                    category="Demo: Functional beverages",
                    reason="Demo mode (no LLM key).",
                    region="Asia",
                    growthIndicator="Rising",
                ),
                MacroSuggestionPayload(
                    category="Demo: Convenience frozen items",
                    reason="Demo mode (no LLM key).",
                    region="Asia",
                    growthIndicator="Mixed",
                ),
                MacroSuggestionPayload(
                    category="Demo: Better-for-you sauces",
                    reason="Demo mode (no LLM key).",
                    region="Asia",
                    growthIndicator="Rising",
                ),
                MacroSuggestionPayload(
                    category="Demo: Premium instant noodles",
                    reason="Demo mode (no LLM key).",
                    region="Asia",
                    growthIndicator="Positive",
                ),
            ]
        grounding_tool = google_types.Tool(google_search=google_types.GoogleSearch())

        response = self.client.models.generate_content(
            model=settings.scan_model,
            contents=(
                "Identify 5 high-velocity CPG item categories worth scanning next for a US importer. "
                "Focus on Asia-forward, under-distributed categories.\n\n"
                "Return ONLY valid JSON as an array of objects with keys: "
                "category, reason, region, growthIndicator."
            ),
            config=google_types.GenerateContentConfig(
                tools=[grounding_tool],
                system_instruction=(
                    "You are MacroScout for PopSight. Use current April 2026 market context and "
                    "prioritize categories with strong signal, concrete buyer relevance, and specific "
                    "regional origin."
                ),
            ),
        )

        payload = self._extract_json(response.text, default=[])
        return [MacroSuggestionPayload.model_validate(item) for item in payload]

    async def run_grounded_scan(self, topic: str) -> dict[str, Any]:
        self.ensure_clients()
        if self.demo_mode:
            digest = hashlib.sha256(topic.encode("utf-8")).hexdigest()
            base = int(digest[:2], 16)
            traction_a = 55 + (base % 35)
            traction_b = 40 + ((base * 3) % 45)
            return {
                "summary": f"Demo scan for topic: {topic}. (No GEMINI/GOOGLE API key configured.)",
                "trends": [
                    {
                        "id": "trend-demo-1",
                        "topic": f"{topic} — retail velocity",
                        "category": "Demand",
                        "growth": "Emerging",
                        "sentiment": "Mixed",
                        "topKeywords": ["demo", "velocity", "trial"],
                    },
                    {
                        "id": "trend-demo-2",
                        "topic": f"{topic} — supply risk",
                        "category": "Supply Chain",
                        "growth": "Watch",
                        "sentiment": "Neutral",
                        "topKeywords": ["demo", "lead time", "substitute"],
                    },
                ],
                "opportunities": [
                    {
                        "id": "product-demo-1",
                        "name": f"{topic} Starter Pack",
                        "brand": "DemoBrand",
                        "category": "Demo Category",
                        "origin": "Demo Origin",
                        "tractionScore": traction_a,
                        "velocity": "Rising",
                        "distributionStatus": "Under-distributed",
                        "pricePoint": "$$",
                        "description": "Demo opportunity item generated without external LLM.",
                        "image": None,
                    },
                    {
                        "id": "product-demo-2",
                        "name": f"{topic} Limited Run",
                        "brand": "DemoBrand",
                        "category": "Demo Category",
                        "origin": "Demo Origin",
                        "tractionScore": traction_b,
                        "velocity": "Stable",
                        "distributionStatus": "Not in US",
                        "pricePoint": "$$$",
                        "description": "Demo opportunity item generated without external LLM.",
                        "image": None,
                    },
                ],
                "manufacturers": [
                    {
                        "id": "mfg-demo-1",
                        "name": "Demo Manufacturer Co.",
                        "location": "Demo City, Demo Country",
                        "specialization": ["Co-packing", "Export docs"],
                        "capacity": "Medium",
                        "contactStatus": "Identified",
                    }
                ],
                "signals": [
                    {
                        "agentName": "System",
                        "message": "Running in demo mode because GEMINI/GOOGLE API key is not set.",
                        "type": "warning",
                    }
                ],
            }
        grounding_tool = google_types.Tool(google_search=google_types.GoogleSearch())
        response = self.client.models.generate_content(
            model=settings.scan_model,
            contents=(
                f"Analyze this CPG sourcing topic in depth: {topic}\n\n"
                "Return ONLY valid JSON with keys: summary, trends, opportunities, manufacturers, signals.\n"
                "trends: array of {id, topic, category, growth, sentiment, topKeywords}\n"
                "opportunities: array of {id, name, brand, category, origin, tractionScore, velocity, distributionStatus, pricePoint, description}\n"
                "manufacturers: array of {id, name, location, specialization, capacity, contactStatus}\n"
                "signals: array of {agentName, message, type}"
            ),
            config=google_types.GenerateContentConfig(
                tools=[grounding_tool],
                system_instruction=(
                    "You are the PopSight core intelligence engine coordinating MarketCrawler, "
                    "TrendAnalyst, ProductSleuth, SupplyPartner, and Strategist. Use current market "
                    "context and return concrete sourcing-ready JSON."
                ),
            ),
        )

        return self._extract_json(response.text, default={})

    def _extract_json(self, raw_text: str | None, default: Any) -> Any:
        if not raw_text:
            return default

        text = raw_text.strip()
        candidates = [text]

        fenced = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
        candidates.extend(item.strip() for item in fenced if item.strip())

        array_match = re.search(r"(\[[\s\S]*\])", text)
        if array_match:
            candidates.append(array_match.group(1).strip())

        object_match = re.search(r"(\{[\s\S]*\})", text)
        if object_match:
            candidates.append(object_match.group(1).strip())

        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

        return default
