"""
Product Discovery LangGraph (Phase 1–2): six parallel retail lanes.

Each lane: Google Trends (Node 0) → MacroScout (Node 1) → Amazon crawl rh=n:16310101 Top 5 (Node 2)
→ NLP/FDA/GLiNER (Node 3).

Phase 3 keys exist on DiscoveryState for a future DAG; they stay empty here.

Persistence: each node calls `repository.add_agent_log` (main DB: Postgres or SQLite). LangGraph also
writes checkpoints to `settings.checkpoints_path` (separate SQLite file). Discovery results
themselves are not stored as products or scan sessions — only returned in the HTTP response.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Literal, TypedDict

import httpx
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from .config import settings
from .discovery_lanes import blueprints_for_lane_ids, fresh_lane_state, trend_query_variants
from .llm import LLMService
from .pipeline.compressor import compress_amazon_organic_item
from .pipeline.gliner_service import enrich_items_with_gliner
from .pipeline.macro_market_crawl import crawl_amazon_food_top_organics
from .pipeline.serp_google_trends import fetch_related_queries_rising_with_query_fallbacks
from .repository_factory import RepositoryLike


def _discovery_timing_print(node_label: str, started: float) -> None:
    """Wall time for one graph node; prints to stdout so uvicorn console always shows it."""
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    print(f"[discovery timing] {node_label}: {elapsed_ms:.1f} ms", flush=True)


class DiscoveryLaneState(TypedDict, total=False):
    category_id: str
    category_label: str
    trends_seed: str
    google_trends_signals: list[dict[str, Any]]
    amazon_search_terms: list[dict[str, str]]
    raw_amazon_data: list[dict[str, Any]]
    compressed_items: list[dict[str, Any]]


class DiscoveryState(TypedDict, total=False):
    user_id: str
    google_trends_geo: str
    amazon_domain: str
    discovery_lane_ids: list[str]
    lanes: list[DiscoveryLaneState]

    google_trends_signals: list[dict[str, Any]]
    amazon_search_terms: list[dict[str, str]]
    raw_amazon_data: list[dict[str, Any]]
    compressed_items: list[dict[str, Any]]

    ranked_product_list: list[dict[str, Any]]
    final_actionable_list: list[dict[str, Any]]
    executive_summary: str

    discovery_pipeline_aborted: bool
    discovery_abort_reason: str


def _lane_has_usable_trends(lane: dict[str, Any]) -> bool:
    """At least one RELATED_QUERIES rising row with a non-empty query (not only SerpAPI error rows)."""
    for s in lane.get("google_trends_signals") or []:
        if isinstance(s, dict) and str(s.get("query") or "").strip():
            return True
    return False


def _aggregate_lanes(lanes: list[dict[str, Any]]) -> dict[str, Any]:
    g: list[dict[str, Any]] = []
    a: list[dict[str, str]] = []
    r: list[dict[str, Any]] = []
    c: list[dict[str, Any]] = []
    for lane in lanes:
        g.extend(lane.get("google_trends_signals") or [])
        a.extend(lane.get("amazon_search_terms") or [])
        r.extend(lane.get("raw_amazon_data") or [])
        c.extend(lane.get("compressed_items") or [])
    return {
        "google_trends_signals": g,
        "amazon_search_terms": a,
        "raw_amazon_data": r,
        "compressed_items": c,
    }


class DiscoveryPipelineRunner:
    """LangGraph DAG: Node 0–3 × six independent category lanes (serialized inside each node)."""

    def __init__(self, *, repository: RepositoryLike, llm_service: LLMService) -> None:
        self.repository = repository
        self.llm_service = llm_service

    async def _fetch_google_trends_one_lane(
        self,
        client: httpx.AsyncClient,
        lane: dict[str, Any],
        *,
        api_key: str,
        geo: str,
        user_id: str,
    ) -> None:
        """SerpAPI Google Trends for one lane (query variants stay sequential inside Serp helper)."""
        seed = lane["trends_seed"]
        cid = str(lane.get("category_id") or "")
        variants = trend_query_variants(category_id=cid, primary_seed=seed)
        try:
            rows, meta = await fetch_related_queries_rising_with_query_fallbacks(
                client,
                api_key=api_key,
                query_variants=variants,
                geo=geo,
                signal_seed_label=seed,
            )
        except Exception as e:
            lane["google_trends_signals"] = [
                {
                    "seed_category": seed,
                    "query": "",
                    "growth": "",
                    "growth_extracted": None,
                    "error": str(e)[:240],
                    "trends_variants_tried": list(variants),
                }
            ]
            return
        lane["google_trends_signals"] = rows
        win = meta.get("winning_trends_query")
        if win:
            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="fetch_market_signals",
                message=f'Node 0 lane {cid}: rising data via Trends q="{win}" (seed label "{seed}").',
                log_type="info",
            )

    async def _fetch_market_signals(self, state: DiscoveryState) -> DiscoveryState:
        t0 = time.perf_counter()
        try:
            user_id = state.get("user_id") or "default-user"
            geo = (state.get("google_trends_geo") or "US").strip() or "US"
            api_key = settings.serpapi_api_key.strip()
            bps = blueprints_for_lane_ids(state.get("discovery_lane_ids"))
            lanes = [fresh_lane_state(bp) for bp in bps]

            if not api_key:
                self.repository.add_agent_log(
                    user_id=user_id,
                    agent_name="fetch_market_signals",
                    message="Missing SERPAPI_API_KEY; all lane trend signals empty.",
                    log_type="error",
                )
                agg = _aggregate_lanes(lanes)
                return {
                    "lanes": lanes,
                    **agg,
                    "ranked_product_list": [],
                    "final_actionable_list": [],
                    "executive_summary": "",
                    "discovery_pipeline_aborted": False,
                    "discovery_abort_reason": "",
                }

            async with httpx.AsyncClient(headers={"User-Agent": "popsight-pipeline/1.0"}) as client:
                # Parallel across lanes: wall time ≈ slowest lane instead of sum(all lanes).
                await asyncio.gather(
                    *[
                        self._fetch_google_trends_one_lane(
                            client, lane, api_key=api_key, geo=geo, user_id=user_id
                        )
                        for lane in lanes
                    ]
                )

            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="fetch_market_signals",
                message=f"Node 0: RELATED_QUERIES rising fetched for {len(lanes)} category lanes.",
                log_type="info",
            )
            agg = _aggregate_lanes(lanes)
            return {
                "lanes": lanes,
                **agg,
                "ranked_product_list": [],
                "final_actionable_list": [],
                "executive_summary": "",
                "discovery_pipeline_aborted": False,
                "discovery_abort_reason": "",
            }
        finally:
            _discovery_timing_print("Node 0 (Google Trends / SerpAPI)", t0)

    def _route_after_node0(self, state: DiscoveryState) -> Literal["continue", "abort"]:
        lanes = list(state.get("lanes") or [])
        if any(_lane_has_usable_trends(ln) if isinstance(ln, dict) else False for ln in lanes):
            return "continue"
        return "abort"

    async def _abort_after_failed_trends(self, state: DiscoveryState) -> DiscoveryState:
        """Skip MacroScout / Amazon / NLP when no lane has usable rising queries (save SerpAPI + LLM)."""
        t0 = time.perf_counter()
        try:
            user_id = state.get("user_id") or "default-user"
            lanes = list(state.get("lanes") or [])
            for lane in lanes:
                if not isinstance(lane, dict):
                    continue
                lane["amazon_search_terms"] = []
                lane["raw_amazon_data"] = []
                lane["compressed_items"] = []
            reason = (
                "No usable Google Trends RELATED_QUERIES (rising) rows for any selected lane "
                "(only errors or empty queries). Skipped MacroScout, Amazon crawl, and compression to save API quota."
            )
            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="fetch_market_signals",
                message=reason,
                log_type="warning",
            )
            agg = _aggregate_lanes([ln for ln in lanes if isinstance(ln, dict)])
            return {
                "lanes": lanes,
                **agg,
                "ranked_product_list": [],
                "final_actionable_list": [],
                "executive_summary": "",
                "discovery_pipeline_aborted": True,
                "discovery_abort_reason": reason,
            }
        finally:
            _discovery_timing_print("abort (clear downstream after Node 0)", t0)

    async def _macro_scout_agent(self, state: DiscoveryState) -> DiscoveryState:
        t0 = time.perf_counter()
        try:
            user_id = state.get("user_id") or "default-user"
            lanes = list(state.get("lanes") or [])
            ran = 0
            skipped = 0
            for lane in lanes:
                if not isinstance(lane, dict):
                    continue
                if not _lane_has_usable_trends(lane):
                    lane["amazon_search_terms"] = []
                    skipped += 1
                    continue
                terms = await self.llm_service.macro_scout_amazon_search_terms_for_lane(
                    lane.get("google_trends_signals") or [],
                    category_id=str(lane.get("category_id") or ""),
                    category_label=str(lane.get("category_label") or ""),
                    max_terms=4,
                )
                lane["amazon_search_terms"] = terms
                ran += 1

            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="MacroScout_Agent",
                message=f"Node 1: MacroScout ran for {ran} lane(s); skipped {skipped} lane(s) with no usable Trends signals.",
                log_type="info",
            )
            agg = _aggregate_lanes(lanes)
            return {"lanes": lanes, **agg}
        finally:
            _discovery_timing_print("Node 1 (MacroScout / LLM)", t0)

    async def _market_crawler(self, state: DiscoveryState) -> DiscoveryState:
        t0 = time.perf_counter()
        try:
            user_id = state.get("user_id") or "default-user"
            lanes = list(state.get("lanes") or [])
            api_key = settings.serpapi_api_key.strip()
            domain = (state.get("amazon_domain") or "amazon.com").strip() or "amazon.com"

            if not api_key:
                self.repository.add_agent_log(
                    user_id=user_id,
                    agent_name="Market_Crawler",
                    message="Missing SERPAPI_API_KEY; skipping Amazon crawl for all lanes.",
                    log_type="warning",
                )
                agg = _aggregate_lanes(lanes)
                return {"lanes": lanes, **agg}

            for lane in lanes:
                terms = lane.get("amazon_search_terms") or []
                if not terms:
                    lane["raw_amazon_data"] = []
                    continue
                raw = await crawl_amazon_food_top_organics(
                    amazon_search_terms=terms,
                    api_key=api_key,
                    amazon_domain=domain,
                    top_n=5,
                )
                lane["raw_amazon_data"] = raw

            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="Market_Crawler",
                message="Node 2: Amazon Grocery (n:16310101) top-5-by-reviews per lane.",
                log_type="info",
            )
            agg = _aggregate_lanes(lanes)
            return {"lanes": lanes, **agg}
        finally:
            _discovery_timing_print("Node 2 (Amazon SerpAPI crawl)", t0)

    async def _nlp_compressor(self, state: DiscoveryState) -> DiscoveryState:
        t0 = time.perf_counter()
        try:
            user_id = state.get("user_id") or "default-user"
            lanes = list(state.get("lanes") or [])

            for lane in lanes:
                raw_rows = lane.get("raw_amazon_data") or []
                items: list[dict[str, Any]] = []
                for raw in raw_rows:
                    if not isinstance(raw, dict):
                        continue
                    compressed = compress_amazon_organic_item(raw)
                    if compressed is None:
                        continue
                    items.append(compressed)

                if settings.gliner_enabled and items:
                    items = await asyncio.to_thread(
                        enrich_items_with_gliner,
                        items,
                        model_id=settings.gliner_model_id,
                        threshold=settings.gliner_threshold,
                        max_input_chars=settings.gliner_max_input_chars,
                        batch_size=settings.gliner_batch_size,
                        console_samples=settings.gliner_console_samples,
                    )
                elif items:
                    for it in items:
                        it.setdefault("gliner_entities", [])
                        it.setdefault("item_entities_compact", "")

                lane["compressed_items"] = items

            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="NLP_Compressor",
                message=f"Node 3: compressed items for {len(lanes)} lanes (FDA + optional GLiNER).",
                log_type="info",
            )
            agg = _aggregate_lanes(lanes)
            return {
                "lanes": lanes,
                **agg,
                "ranked_product_list": [],
                "final_actionable_list": [],
                "executive_summary": "",
            }
        finally:
            gliner = "on" if settings.gliner_enabled else "off"
            _discovery_timing_print(f"Node 3 (compress + FDA + GLiNER {gliner})", t0)

    async def run(
        self,
        *,
        user_id: str = "default-user",
        google_trends_geo: str = "US",
        amazon_domain: str = "amazon.com",
        discovery_lane_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        lane_filter: list[str] = []
        if discovery_lane_ids:
            lane_filter = list(dict.fromkeys(discovery_lane_ids))

        async with AsyncSqliteSaver.from_conn_string(settings.checkpoints_path) as checkpointer:
            graph = StateGraph(DiscoveryState)
            graph.add_node("fetch_market_signals", self._fetch_market_signals)
            graph.add_node("abort_after_failed_trends", self._abort_after_failed_trends)
            graph.add_node("macro_scout_agent", self._macro_scout_agent)
            graph.add_node("market_crawler", self._market_crawler)
            graph.add_node("nlp_compressor", self._nlp_compressor)

            graph.add_edge(START, "fetch_market_signals")
            graph.add_conditional_edges(
                "fetch_market_signals",
                self._route_after_node0,
                {
                    "continue": "macro_scout_agent",
                    "abort": "abort_after_failed_trends",
                },
            )
            graph.add_edge("abort_after_failed_trends", END)
            graph.add_edge("macro_scout_agent", "market_crawler")
            graph.add_edge("market_crawler", "nlp_compressor")
            graph.add_edge("nlp_compressor", END)

            compiled = graph.compile(checkpointer=checkpointer)
            t_run = time.perf_counter()
            try:
                return await compiled.ainvoke(
                    {
                        "user_id": user_id,
                        "google_trends_geo": google_trends_geo,
                        "amazon_domain": amazon_domain,
                        "discovery_lane_ids": lane_filter,
                    },
                    {"configurable": {"thread_id": f"discovery::{user_id}::{uuid.uuid4().hex[:10]}"}},
                )
            finally:
                _discovery_timing_print("TOTAL (LangGraph ainvoke, all nodes)", t_run)


# Backwards-compatible alias for imports expecting the old name.
MacroColdStartRunner = DiscoveryPipelineRunner
