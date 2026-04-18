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

MACRO_SCOUT_AMAZON_SYSTEM_PROMPT = (
    "You are the lead strategic planner for Taizi Hang (importer). Using today's Google Trends breakout queries, "
    "and the company's edge in ginger and ginseng supply chains, produce exactly six precise Amazon long-tail "
    'search terms. Return ONLY valid JSON: [{"category": "...", "search_term": "..."}]'
)


def _macro_scout_lane_system_prompt(*, category_label: str, category_id: str, max_terms: int) -> str:
    return (
        f'You are the lead strategic planner for Taizi Hang (PoP). Scope: ONE retail aisle only — "{category_label}" '
        f'(category_id: {category_id}). Using the rising-query JSON for this aisle, propose between 2 and {max_terms} '
        "precise Amazon US long-tail `search_term` strings shoppers would type. "
        f'Every object must set `"category"` to exactly "{category_label}". '
        'Return ONLY valid JSON: [{"category": "...", "search_term": "..."}]'
    )


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

    async def macro_scout_amazon_search_terms(self, google_trends_signals: list[dict]) -> list[dict[str, str]]:
        """
        MacroScout_Agent (Phase 1): JSON [{category, search_term}] from Trends plus Taizi Hang guardrails.
        """
        usable = [s for s in google_trends_signals if isinstance(s, dict) and str(s.get("query") or "").strip()]
        self.ensure_clients()
        if self.demo_mode or self.chat_model is None:
            out: list[dict[str, str]] = []
            for s in usable[:6]:
                out.append(
                    {
                        "category": str(s.get("seed_category") or "Trend")[:120],
                        "search_term": str(s.get("query") or "")[:200],
                    }
                )
            while len(out) < 6 and usable:
                # pad from remaining
                for s in usable[len(out) :]:
                    out.append(
                        {
                            "category": str(s.get("seed_category") or "Trend")[:120],
                            "search_term": str(s.get("query") or "")[:200],
                        }
                    )
                    if len(out) >= 6:
                        break
            while len(out) < 6:
                out.append({"category": "Demo", "search_term": "asian ginger tea instant packets"})
            return out[:12]

        assert self.chat_model is not None
        import json

        from langchain_core.messages import HumanMessage, SystemMessage

        payload = json.dumps(usable[:80], ensure_ascii=False, indent=2)
        human = (
            "Today's Google Trends RELATED_QUERIES (rising) signals as JSON:\n"
            f"{payload}\n\n"
            "Taizi Hang sourcing guardrails (must follow):\n"
            "- Prefer shelf-stable packaged foods with shelf life clearly above 12 months; avoid short-dated SKUs "
            "and heavy cold-chain dependence.\n"
            "- Do not target raw/fresh categories (raw meat, live seafood, fresh-cut ready-to-eat produce, etc.).\n"
            "- Lean on ginger and red ginseng supply-chain strengths: favor long-tail Amazon queries where those "
            "ingredients, herbal warming, functional beverages, or Asian snacks fit naturally.\n\n"
            "Output ONLY a JSON array. No prose, no markdown fences."
        )
        messages = [
            SystemMessage(content=MACRO_SCOUT_AMAZON_SYSTEM_PROMPT),
            HumanMessage(content=human),
        ]
        try:
            result = await self.chat_model.ainvoke(messages)
        except Exception:
            fallback: list[dict[str, str]] = []
            for s in usable[:6]:
                fallback.append(
                    {
                        "category": str(s.get("seed_category") or "Trend")[:120],
                        "search_term": str(s.get("query") or "")[:200],
                    }
                )
            return fallback[:12] or [{"category": "Fallback", "search_term": "korean red ginseng instant tea mix"}]

        text = getattr(result, "content", None) or getattr(result, "text", None) or str(result)
        raw_list = self._extract_json(text if isinstance(text, str) else str(text), default=[])
        if not isinstance(raw_list, list):
            raw_list = []
        validated: list[dict[str, str]] = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            cat = str(item.get("category") or "").strip()
            term = str(item.get("search_term") or "").strip()
            if not term:
                continue
            validated.append({"category": cat or "General", "search_term": term[:400]})
        if not validated and usable:
            fb: list[dict[str, str]] = []
            for s in usable[:6]:
                fb.append(
                    {
                        "category": str(s.get("seed_category") or "Trend")[:120],
                        "search_term": str(s.get("query") or "")[:200],
                    }
                )
            return fb[:12]
        return validated[:12]

    async def macro_scout_amazon_search_terms_for_lane(
        self,
        google_trends_signals: list[dict],
        *,
        category_id: str,
        category_label: str,
        max_terms: int = 4,
    ) -> list[dict[str, str]]:
        """
        MacroScout per retail lane: JSON [{category, search_term}] scoped to one of six discovery aisles.
        """
        cap = max(2, min(max_terms, 6))
        usable = [s for s in google_trends_signals if isinstance(s, dict) and str(s.get("query") or "").strip()]
        self.ensure_clients()
        if self.demo_mode or self.chat_model is None:
            out: list[dict[str, str]] = []
            for s in usable[:cap]:
                out.append(
                    {
                        "category": category_label[:120] or category_id,
                        "search_term": str(s.get("query") or "")[:200],
                    }
                )
            while len(out) < 2:
                out.append(
                    {
                        "category": category_label[:120] or category_id,
                        "search_term": f"{category_label} variety pack amazon".strip()[:200],
                    }
                )
            return out[:cap]

        assert self.chat_model is not None
        import json

        from langchain_core.messages import HumanMessage, SystemMessage

        payload = json.dumps(usable[:40], ensure_ascii=False, indent=2)
        human = (
            f"Aisle: {category_label} (id: {category_id})\n"
            "Google Trends RELATED_QUERIES (rising) for this aisle only:\n"
            f"{payload}\n\n"
            "Taizi Hang sourcing guardrails (must follow):\n"
            "- Prefer shelf-stable packaged foods with shelf life clearly above 12 months; avoid short-dated SKUs "
            "and heavy cold-chain dependence.\n"
            "- Do not target raw/fresh categories (raw meat, live seafood, fresh-cut ready-to-eat produce, etc.).\n"
            "- Lean on ginger and red ginseng supply-chain strengths where relevant for this aisle.\n\n"
            "Output ONLY a JSON array. No prose, no markdown fences."
        )
        messages = [
            SystemMessage(content=_macro_scout_lane_system_prompt(category_label=category_label, category_id=category_id, max_terms=cap)),
            HumanMessage(content=human),
        ]
        try:
            result = await self.chat_model.ainvoke(messages)
        except Exception:
            fb: list[dict[str, str]] = []
            for s in usable[:cap]:
                fb.append(
                    {
                        "category": category_label[:120] or category_id,
                        "search_term": str(s.get("query") or "")[:200],
                    }
                )
            return fb[:cap] or [
                {
                    "category": category_label[:120] or category_id,
                    "search_term": f"{category_label} multipack".strip()[:200],
                }
            ]

        text = getattr(result, "content", None) or getattr(result, "text", None) or str(result)
        raw_list = self._extract_json(text if isinstance(text, str) else str(text), default=[])
        if not isinstance(raw_list, list):
            raw_list = []
        validated: list[dict[str, str]] = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            term = str(item.get("search_term") or "").strip()
            if not term:
                continue
            validated.append({"category": category_label[:120] or category_id, "search_term": term[:400]})
        if not validated and usable:
            for s in usable[:cap]:
                validated.append(
                    {
                        "category": category_label[:120] or category_id,
                        "search_term": str(s.get("query") or "")[:200],
                    }
                )
        return validated[:cap]

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
