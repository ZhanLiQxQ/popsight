from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from google import genai
from google.genai import types as google_types
from google.genai.errors import ClientError
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError

from .config import settings
from .schemas import MacroSuggestionPayload


class LLMService:
    def __init__(self) -> None:
        self.client = None
        self.chat_model = None
        self.demo_mode = False

    def ensure_clients(self) -> None:
        if settings.ollama_base_url:
            if self.chat_model is None:
                from langchain_ollama import ChatOllama

                self.chat_model = ChatOllama(
                    model=settings.chat_model,
                    base_url=settings.ollama_base_url.rstrip("/"),
                    temperature=0.2,
                )
            if settings.gemini_api_key and self.client is None:
                self.client = genai.Client(api_key=settings.gemini_api_key)
            return

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
        assert self.chat_model is not None

        prompt = (
            "You are MacroScout for a CPG importer.\n"
            "Task: generate EXACTLY 5 pan-Asia CPG macro trends that are specific and actionable.\n"
            "Constraints:\n"
            "- Each trend must be a concrete product-style/format, not a generic category.\n"
            '- category example format: "Herbal Sparkling Water", "Yuzu Collagen Jelly Drink".\n'
            "- Keep them plausible for 2026 and relevant for US importing.\n"
            "- Return ONLY valid JSON: an array of 5 objects.\n"
            "- Keys: category, reason, region, growthIndicator.\n"
            "- region should be a specific sub-region or country cluster (e.g., 'Japan', 'Korea', 'SEA', 'Taiwan', 'China').\n"
            "- growthIndicator should be a short phrase like 'Rising', 'Explosive', 'Steady', 'Early'.\n"
        )

        try:
            result = await self.chat_model.ainvoke(prompt)
        except Exception:
            # If rate-limited, fall back to a deterministic placeholder set to keep UX unblocked.
            return [
                MacroSuggestionPayload(
                    category="Herbal Sparkling Water",
                    reason="Low sugar + functional positioning; strong fit for pan-Asia flavor cues.",
                    region="Japan/Korea",
                    growthIndicator="Rising",
                ),
                MacroSuggestionPayload(
                    category="Yuzu Collagen Jelly Drink",
                    reason="Portable texture-drink format with beauty/functional framing.",
                    region="Japan",
                    growthIndicator="Rising",
                ),
                MacroSuggestionPayload(
                    category="Coconut Water + Electrolyte Sachets",
                    reason="Hydration booster add-on format; easy import bundle strategy.",
                    region="SEA",
                    growthIndicator="Steady",
                ),
                MacroSuggestionPayload(
                    category="Tea-Based Probiotic Soda",
                    reason="Soda replacement with gut-health claim adjacency.",
                    region="Korea/Taiwan",
                    growthIndicator="Early",
                ),
                MacroSuggestionPayload(
                    category="Spicy Umami Snack Mix (Seaweed/Nuts)",
                    reason="Cross-over snack profile; good for Asian grocery + mainstream trial.",
                    region="China/Taiwan",
                    growthIndicator="Rising",
                ),
            ]
        text = getattr(result, "content", None) or getattr(result, "text", None) or str(result)
        payload = self._extract_json(text if isinstance(text, str) else str(text), default=[])
        if not isinstance(payload, list):
            payload = []
        validated: list[MacroSuggestionPayload] = []
        for item in payload[:5]:
            try:
                validated.append(MacroSuggestionPayload.model_validate(item))
            except Exception:
                continue
        return validated[:5]

    async def macro_scout_amazon_search_terms_for_lane(
        self,
        trends_signals: list[dict[str, Any]],
        *,
        category_id: str,
        category_label: str,
        max_terms: int = 4,
    ) -> list[dict[str, str]]:
        """
        Node 1 of the discovery graph: turn one lane's Google Trends rising queries into
        up to ``max_terms`` Amazon search strings.

        Returns a list of ``{"category": category_label, "search_term": str}`` rows.
        Falls back to the raw trend queries (or the category label) if the LLM is absent
        or returns unusable JSON, so the pipeline never hard-fails here.
        """
        self.ensure_clients()

        rising_queries: list[str] = []
        seen: set[str] = set()
        for row in trends_signals:
            if not isinstance(row, dict):
                continue
            q = str(row.get("query") or "").strip()
            if not q:
                continue
            key = q.lower()
            if key in seen:
                continue
            seen.add(key)
            rising_queries.append(q)

        def _fallback_terms() -> list[dict[str, str]]:
            seeds = rising_queries or [category_label]
            out: list[dict[str, str]] = []
            emitted: set[str] = set()
            for q in seeds:
                s = q.strip()
                if not s:
                    continue
                key = s.lower()
                if key in emitted:
                    continue
                emitted.add(key)
                out.append({"category": category_label, "search_term": s})
                if len(out) >= max(1, max_terms):
                    break
            return out

        if self.demo_mode or self.chat_model is None or not rising_queries:
            return _fallback_terms()

        trend_lines = "\n".join(f"- {q}" for q in rising_queries[:10])
        prompt = (
            "You are MacroScout translating Google Trends rising queries into Amazon search terms "
            f"for a CPG importer. Retail lane: \"{category_label}\" (id: {category_id}).\n\n"
            "Rising queries (most recent first):\n"
            f"{trend_lines}\n\n"
            f"Task: produce UP TO {max_terms} high-signal Amazon search strings for this lane.\n"
            "Rules:\n"
            "- Each search_term must be how a real shopper types it into Amazon (2-5 words).\n"
            "- Stay inside the retail lane; do not drift into unrelated categories.\n"
            "- Prefer product formats over brand names unless the brand is the trend driver.\n"
            "- No duplicates; no punctuation other than spaces.\n"
            "- Return ONLY valid JSON: an array of objects, each with keys "
            '"category" and "search_term". "category" must be the lane label verbatim.\n'
        )

        try:
            result = await self.chat_model.ainvoke(prompt)
        except Exception:
            return _fallback_terms()

        text = getattr(result, "content", None) or getattr(result, "text", None) or str(result)
        payload = self._extract_json(text if isinstance(text, str) else str(text), default=[])
        if not isinstance(payload, list):
            return _fallback_terms()

        terms: list[dict[str, str]] = []
        emitted: set[str] = set()
        for item in payload:
            if not isinstance(item, dict):
                continue
            term = str(item.get("search_term") or "").strip()
            if not term:
                continue
            key = term.lower()
            if key in emitted:
                continue
            emitted.add(key)
            terms.append({"category": category_label, "search_term": term})
            if len(terms) >= max(1, max_terms):
                break

        return terms or _fallback_terms()

    async def web_snippets(self, query: str, *, max_items: int = 8) -> list[str]:
        """
        Use Google Search grounding once to retrieve a compact set of snippets.
        This is the only place we should hit external web search in the deep-dive graph.
        """
        self.ensure_clients()
        if self.demo_mode:
            return [f"Demo snippet for query: {query}"]

        assert self.client is not None
        grounding_tool = google_types.Tool(google_search=google_types.GoogleSearch())
        try:
            response = self.client.models.generate_content(
                model=settings.scan_model,
                contents=(
                    f"Search the web for: {query}\n"
                    f"Return a compact list of up to {max_items} factual snippets.\n"
                    "Each item should be one line string formatted as: 'SOURCE: <site> | <snippet>'.\n"
                    "Return ONLY valid JSON: an array of strings."
                ),
                config=google_types.GenerateContentConfig(tools=[grounding_tool]),
            )
            payload = self._extract_json(response.text, default=[])
            if isinstance(payload, list):
                items = [str(x).strip() for x in payload if str(x).strip()]
                return items[:max_items]
            text = str(response.text or "").strip()
            return [text][:max_items] if text else []
        except Exception as e:
            # 429/503 and other transient failures should not crash the scan graph.
            status = getattr(e, "status_code", "")
            return [f"SOURCE: gemini | crawler_error: {status} {str(e)[:160]}"]

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
