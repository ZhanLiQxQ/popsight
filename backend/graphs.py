from __future__ import annotations

import asyncio
import operator
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langchain.agents import create_agent
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from .config import settings
from .llm import LLMService
from .repository_factory import RepositoryLike
from .vector_store import vector_store


class DeepDiveState(TypedDict, total=False):
    user_id: str
    topic: str
    conversation_id: str
    scan_session_id: str
    search_queries: list[str]
    raw_market_data: Annotated[list[str], operator.add]
    trend_report: list[dict]
    target_products: list[dict]
    suppliers: list[dict]
    final_summary: str


@dataclass
class ChatContext:
    user_id: str
    conversation_id: str
    scan_session_id: str | None = None
    selected_product_id: str | None = None


class ChatState(TypedDict, total=False):
    user_id: str
    conversation_id: str
    scan_session_id: str | None
    selected_product_id: str | None
    user_message: str
    response: str
    rag_context: str
    messages: list[Any]


class GraphService:
    def __init__(self, repository: RepositoryLike, llm_service: LLMService, checkpoints_path: str, root_dir: Path):
        self.repository = repository
        self.llm_service = llm_service
        self.checkpoints_path = checkpoints_path
        self.root_dir = root_dir

    async def scan_topic(self, *, user_id: str, topic: str) -> dict[str, Any]:
        async with AsyncSqliteSaver.from_conn_string(self.checkpoints_path) as checkpointer:
            graph = StateGraph(DeepDiveState)
            graph.add_node("strategist_init", self._strategist_init)
            graph.add_node("market_crawler", self._market_crawler)
            graph.add_node("trend_analyst", self._trend_analyst)
            graph.add_node("product_sleuth", self._product_sleuth)
            graph.add_node("supply_partner", self._supply_partner)
            graph.add_node("strategist_final", self._strategist_final)
            graph.add_node("persist_scan", self._persist_deep_dive)

            graph.add_edge(START, "strategist_init")
            graph.add_edge("strategist_init", "market_crawler")
            graph.add_edge("market_crawler", "trend_analyst")
            graph.add_edge("market_crawler", "product_sleuth")
            graph.add_edge("market_crawler", "supply_partner")
            graph.add_edge(["trend_analyst", "product_sleuth", "supply_partner"], "strategist_final")
            graph.add_edge("strategist_final", "persist_scan")
            graph.add_edge("persist_scan", END)

            compiled = graph.compile(checkpointer=checkpointer)
            state = await compiled.ainvoke(
                {"user_id": user_id, "topic": topic},
                {"configurable": {"thread_id": f"scan::{user_id}::{topic}"}},
            )
        return state

    async def chat(
        self,
        *,
        user_id: str,
        conversation_id: str,
        scan_session_id: str | None,
        user_message: str,
        selected_product_id: str | None,
    ) -> dict[str, Any]:
        async with AsyncSqliteSaver.from_conn_string(self.checkpoints_path) as checkpointer:
            graph = StateGraph(ChatState)
            tools = self._build_native_tools()
            tool_node = ToolNode(tools)

            graph.add_node("retrieve_memory", self._retrieve_memory)
            graph.add_node("agent_reply", self._agent_reply)
            graph.add_node("tools", tool_node)

            graph.add_edge(START, "retrieve_memory")
            graph.add_edge("retrieve_memory", "agent_reply")
            graph.add_conditional_edges("agent_reply", tools_condition, {"tools": "tools", END: END})
            graph.add_edge("tools", "agent_reply")
            compiled = graph.compile(checkpointer=checkpointer)
            state = await compiled.ainvoke(
                {
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "scan_session_id": scan_session_id,
                    "selected_product_id": selected_product_id,
                    "user_message": user_message,
                },
                {"configurable": {"thread_id": conversation_id}},
            )
        return state

    async def _strategist_init(self, state: DeepDiveState) -> DeepDiveState:
        self.llm_service.ensure_clients()
        user_id = state["user_id"]
        topic = state["topic"]
        if self.llm_service.demo_mode or self.llm_service.chat_model is None:
            search_queries = [f"{topic} trends 2026", f"{topic} brands SKU price", f"{topic} OEM manufacturer"]
            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="Strategist",
                message="Demo mode: generated heuristic search queries.",
                log_type="warning",
            )
            return {"search_queries": search_queries}
        assert self.llm_service.chat_model is not None

        prompt = (
            "You are Strategist.\n"
            f"Topic: {topic}\n"
            "Generate 3 web search queries to deeply research this topic for CPG sourcing.\n"
            "Return ONLY valid JSON: an array of 3 short strings."
        )
        try:
            result = await asyncio.wait_for(self.llm_service.chat_model.ainvoke(prompt), timeout=18)
        except Exception as e:
            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="Strategist",
                message=f"LLM quota/error while generating queries; using fallback. ({str(e)[:120]})",
                log_type="warning",
            )
            return {"search_queries": [f"{topic} trends 2026", f"{topic} brands SKU price", f"{topic} OEM manufacturer"]}
        text = getattr(result, "content", None) or getattr(result, "text", None) or str(result)
        queries = self.llm_service._extract_json(text if isinstance(text, str) else str(text), default=[])
        if not isinstance(queries, list):
            queries = []
        search_queries = [str(q).strip() for q in queries if str(q).strip()][:3]
        if len(search_queries) < 3:
            search_queries = (search_queries + [f"{topic} trend 2026", f"{topic} brand SKU price", f"{topic} OEM manufacturer"])[:3]

        self.repository.add_agent_log(
            user_id=user_id,
            agent_name="Strategist",
            message=f"Generated {len(search_queries)} search queries for deep dive.",
            log_type="info",
        )
        return {"search_queries": search_queries}

    async def _market_crawler(self, state: DeepDiveState) -> DeepDiveState:
        user_id = state["user_id"]
        queries = state.get("search_queries", [])
        topic = state["topic"]

        all_snippets: list[str] = []
        for query in queries:
            try:
                snippets = await asyncio.wait_for(self.llm_service.web_snippets(query, max_items=8), timeout=12)
            except TimeoutError:
                snippets = [f"SOURCE: timeout | crawler_timeout for query: {query}"]
            all_snippets.extend(snippets)

        self.repository.add_agent_log(
            user_id=user_id,
            agent_name="MarketCrawler",
            message=f'Crawled {len(queries)} queries and collected {len(all_snippets)} snippets for "{topic}".',
            log_type="info",
        )
        print("=== MARKET CRAWLER OUTPUT ===")
        for s in all_snippets[:5]:
            print(s)
        print("=== END ===")
        return {"raw_market_data": all_snippets}

    async def _trend_analyst(self, state: DeepDiveState) -> DeepDiveState:
        self.llm_service.ensure_clients()
        user_id = state["user_id"]
        topic = state["topic"]
        raw = state.get("raw_market_data", [])
        if self.llm_service.demo_mode or self.llm_service.chat_model is None:
            trends = [
                {
                    "id": f"trend-{uuid.uuid4().hex[:8]}",
                    "topic": f"{topic} — flavor & ritual",
                    "category": "Taste",
                    "growth": "Emerging",
                    "sentiment": "Mixed",
                    "topKeywords": ["herbal", "sparkling", "low sugar"],
                }
            ]
            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="TrendAnalyst",
                message="Demo mode: produced a minimal trend report.",
                log_type="warning",
            )
            return {"trend_report": trends}
        assert self.llm_service.chat_model is not None

        prompt = (
            "You are TrendAnalyst.\n"
            "Focus ONLY on consumers: tastes, packaging, and psychology.\n"
            f"Topic: {topic}\n"
            "Evidence snippets:\n"
            + "\n".join(f"- {item}" for item in raw[:80])
            + "\n\nReturn ONLY valid JSON: an array of trend objects with keys:\n"
            "id, topic, category, growth, sentiment, topKeywords.\n"
            "sentiment must be one of: Positive, Neutral, Mixed."
        )
        try:
            result = await asyncio.wait_for(self.llm_service.chat_model.ainvoke(prompt), timeout=22)
        except ChatGoogleGenerativeAIError as e:
            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="TrendAnalyst",
                message=f"LLM quota/error; returning empty trend report. ({str(e)[:120]})",
                log_type="warning",
            )
            return {"trend_report": []}
        except TimeoutError:
            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="TrendAnalyst",
                message="LLM call timed out; returning empty trend report.",
                log_type="warning",
            )
            return {"trend_report": []}
        text = getattr(result, "content", None) or getattr(result, "text", None) or str(result)
        payload = self.llm_service._extract_json(text if isinstance(text, str) else str(text), default=[])
        trends = payload if isinstance(payload, list) else []

        self.repository.add_agent_log(
            user_id=user_id,
            agent_name="TrendAnalyst",
            message=f"Extracted {len(trends)} trend signals.",
            log_type="info",
        )
        return {"trend_report": trends}

    async def _product_sleuth(self, state: DeepDiveState) -> DeepDiveState:
        self.llm_service.ensure_clients()
        user_id = state["user_id"]
        topic = state["topic"]
        raw = state.get("raw_market_data", [])
        if self.llm_service.demo_mode or self.llm_service.chat_model is None:
            products = [
                {
                    "id": f"product-{uuid.uuid4().hex[:8]}",
                    "name": f"{topic} Starter SKU",
                    "brand": "DemoBrand",
                    "category": "Ready-to-drink",
                    "origin": "Korea",
                    "tractionScore": 68,
                    "velocity": "Rising",
                    "distributionStatus": "Under-distributed",
                    "pricePoint": "$$",
                    "description": "Demo SKU (no LLM key / rate limited).",
                    "image": None,
                }
            ]
            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="ProductSleuth",
                message="Demo mode: produced a minimal product list.",
                log_type="warning",
            )
            return {"target_products": products}
        assert self.llm_service.chat_model is not None

        prompt = (
            "You are ProductSleuth.\n"
            "Task: extract concrete brand/SKU opportunities with price points and US distribution gaps.\n"
            f"Topic: {topic}\n"
            "Evidence snippets:\n"
            + "\n".join(f"- {item}" for item in raw[:80])
            + "\n\nReturn ONLY valid JSON: an array of product objects with keys:\n"
            "id, name, brand, category, origin, tractionScore, velocity, distributionStatus, pricePoint, description, image.\n"
            "velocity must be one of: Rising, Explosive, Stable.\n"
            "distributionStatus must be one of: Parallel Import, Under-distributed, Not in US.\n"
        )
        try:
            result = await asyncio.wait_for(self.llm_service.chat_model.ainvoke(prompt), timeout=22)
        except ChatGoogleGenerativeAIError as e:
            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="ProductSleuth",
                message=f"LLM quota/error; returning empty product list. ({str(e)[:120]})",
                log_type="warning",
            )
            return {"target_products": []}
        except TimeoutError:
            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="ProductSleuth",
                message="LLM call timed out; returning empty product list.",
                log_type="warning",
            )
            return {"target_products": []}
        text = getattr(result, "content", None) or getattr(result, "text", None) or str(result)
        payload = self.llm_service._extract_json(text if isinstance(text, str) else str(text), default=[])
        products = payload if isinstance(payload, list) else []

        self.repository.add_agent_log(
            user_id=user_id,
            agent_name="ProductSleuth",
            message=f"Identified {len(products)} high-potential SKUs.",
            log_type="info",
        )
        return {"target_products": products}

    async def _supply_partner(self, state: DeepDiveState) -> DeepDiveState:
        self.llm_service.ensure_clients()
        user_id = state["user_id"]
        topic = state["topic"]
        raw = state.get("raw_market_data", [])
        if self.llm_service.demo_mode or self.llm_service.chat_model is None:
            suppliers = [
                {
                    "id": f"manufacturer-{uuid.uuid4().hex[:8]}",
                    "name": "Demo OEM Beverage Co.",
                    "location": "Taiwan",
                    "specialization": ["RTD tea", "carbonation", "export docs"],
                    "capacity": "Medium",
                    "contactStatus": "Identified",
                }
            ]
            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="SupplyPartner",
                message="Demo mode: produced a minimal supplier list.",
                log_type="warning",
            )
            return {"suppliers": suppliers}
        assert self.llm_service.chat_model is not None

        prompt = (
            "You are SupplyPartner.\n"
            "Task: propose potential OEM/ODM manufacturers and supply chain leads.\n"
            f"Topic: {topic}\n"
            "Evidence snippets:\n"
            + "\n".join(f"- {item}" for item in raw[:80])
            + "\n\nReturn ONLY valid JSON: an array of manufacturer objects with keys:\n"
            "id, name, location, specialization, capacity, contactStatus.\n"
            "capacity must be one of: Low, Medium, High.\n"
            "contactStatus must be one of: Identified, Contacted, Partner."
        )
        try:
            result = await asyncio.wait_for(self.llm_service.chat_model.ainvoke(prompt), timeout=22)
        except ChatGoogleGenerativeAIError as e:
            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="SupplyPartner",
                message=f"LLM quota/error; returning empty supplier list. ({str(e)[:120]})",
                log_type="warning",
            )
            return {"suppliers": []}
        except TimeoutError:
            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="SupplyPartner",
                message="LLM call timed out; returning empty supplier list.",
                log_type="warning",
            )
            return {"suppliers": []}
        text = getattr(result, "content", None) or getattr(result, "text", None) or str(result)
        payload = self.llm_service._extract_json(text if isinstance(text, str) else str(text), default=[])
        suppliers = payload if isinstance(payload, list) else []

        self.repository.add_agent_log(
            user_id=user_id,
            agent_name="SupplyPartner",
            message=f"Found {len(suppliers)} supplier/manufacturer leads.",
            log_type="info",
        )
        return {"suppliers": suppliers}

    async def _strategist_final(self, state: DeepDiveState) -> DeepDiveState:
        self.llm_service.ensure_clients()
        user_id = state["user_id"]
        topic = state["topic"]
        if self.llm_service.demo_mode or self.llm_service.chat_model is None:
            final_summary = (
                f"Demo deep dive summary for: {topic}.\n"
                "LLM key is missing or rate-limited; results are placeholders. Add a proper Gemini key and quota for reliable analysis."
            )
            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="Strategist",
                message="Demo mode: generated placeholder final summary.",
                log_type="warning",
            )
            return {"final_summary": final_summary}
        assert self.llm_service.chat_model is not None

        prompt = (
            "You are Strategist.\n"
            f"Topic: {topic}\n\n"
            "Trends:\n"
            + json_dump(state.get("trend_report", []))
            + "\n\nTarget products:\n"
            + json_dump(state.get("target_products", []))
            + "\n\nSuppliers:\n"
            + json_dump(state.get("suppliers", []))
            + "\n\nWrite a concise sourcing-ready summary in plain text (no JSON)."
        )
        try:
            result = await asyncio.wait_for(self.llm_service.chat_model.ainvoke(prompt), timeout=25)
        except ChatGoogleGenerativeAIError as e:
            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="Strategist",
                message=f"LLM quota/error; returning minimal summary. ({str(e)[:120]})",
                log_type="warning",
            )
            return {"final_summary": f"Deep dive completed for {topic}, but summarization was rate-limited."}
        except TimeoutError:
            self.repository.add_agent_log(
                user_id=user_id,
                agent_name="Strategist",
                message="LLM call timed out during final synthesis; returning minimal summary.",
                log_type="warning",
            )
            return {"final_summary": f"Deep dive completed for {topic}, but synthesis timed out."}
        text = getattr(result, "content", None) or getattr(result, "text", None) or str(result)
        final_summary = text if isinstance(text, str) else str(text)

        self.repository.add_agent_log(
            user_id=user_id,
            agent_name="Strategist",
            message="Synthesized expert findings into final summary.",
            log_type="success",
        )
        return {"final_summary": final_summary}

    async def _persist_deep_dive(self, state: DeepDiveState) -> DeepDiveState:
        user_id = state["user_id"]
        topic = state["topic"]
        summary = state.get("final_summary") or f"Deep dive completed for {topic}."

        trends = ensure_ids(state.get("trend_report", []), prefix="trend")
        products = ensure_ids(state.get("target_products", []), prefix="product")
        suppliers = ensure_ids(state.get("suppliers", []), prefix="manufacturer")

        scan_session = self.repository.create_scan_session(
            user_id=user_id,
            topic=topic,
            summary=summary,
            trends=trends,
            products=products,
            manufacturers=suppliers,
        )
        conversation = self.repository.upsert_conversation(
            user_id=user_id,
            topic=topic,
            title=topic,
            scan_session_id=scan_session.id,
        )

        if not conversation.messages:
            self.repository.add_message(
                conversation_id=conversation.id,
                role="assistant",
                content=(
                    "I know the current scan context and can answer follow-up questions about the "
                    "products, suppliers, and trends you just generated."
                ),
            )

        self.repository.add_agent_log(
            user_id=user_id,
            agent_name="Strategist",
            message=f'Deep dive scan persisted for "{topic}".',
            log_type="success",
        )
        return {"conversation_id": conversation.id, "scan_session_id": scan_session.id}

    async def _agent_reply(self, state: ChatState) -> ChatState:
        self.llm_service.ensure_clients()
        user_id = state["user_id"]
        conversation_id = state["conversation_id"]
        scan_session_id = state.get("scan_session_id")
        selected_product_id = state.get("selected_product_id")
        rag_context = state.get("rag_context", "")
        messages_in = state.get("messages", [])

        await asyncio.to_thread(
            self.repository.add_message,
            conversation_id=conversation_id,
            role="user",
            content=state["user_message"],
            product_ids=[selected_product_id] if selected_product_id else None,
        )
        # Refresh conversation for storage but use message state for agent loop.
        await asyncio.to_thread(self.repository.get_conversation, conversation_id)

        if self.llm_service.chat_model is None or self.llm_service.demo_mode:
            response_text = (
                "当前运行在 Demo/限流模式：我已拿到检索到的上下文，但无法调用 LLM 生成高质量回复。\n\n"
                "你可以：\n"
                "- 配置有效的 `GEMINI_API_KEY`/`GOOGLE_API_KEY`\n"
                "- 或提升 Gemini 配额/等待限流恢复\n\n"
                "已检索上下文（节选）：\n"
                + (rag_context[:1200] if rag_context else "(empty)")
            )
            await asyncio.to_thread(
                self.repository.add_message,
                conversation_id=conversation_id,
                role="assistant",
                content=response_text,
                product_ids=[selected_product_id] if selected_product_id else None,
            )
            await asyncio.to_thread(
                self.repository.add_agent_log,
                user_id=user_id,
                agent_name="Strategist",
                message="Demo/limited mode: returned context-only reply.",
                log_type="warning",
            )
            return {"response": response_text, "messages": list(messages_in) + [AIMessage(content=response_text)]}

        tools = self._build_native_tools()
        system_prompt = (
            "You are the PopSight sourcing copilot.\n"
            "Use tools to inspect the current scan, retrieve relevant memories, and save durable insights only when the "
            "user expresses a lasting preference, decision, supplier note, or reusable buying rule.\n"
            "Keep answers concise, specific, and commercially useful.\n\n"
            "Retrieved context (RAG):\n"
            f"{rag_context}\n"
        )

        try:
            agent = create_agent(
                model=self.llm_service.chat_model,
                tools=tools,
                system_prompt=system_prompt,
                context_schema=ChatContext,
            )

            result = await asyncio.wait_for(
                agent.ainvoke(
                    {"messages": messages_in},
                    context=ChatContext(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        scan_session_id=scan_session_id,
                        selected_product_id=selected_product_id,
                    ),
                ),
                timeout=25,
            )
        except ChatGoogleGenerativeAIError as e:
            response_text = (
                "当前模型调用被限流/配额不足，已返回可用上下文。请稍后重试或更换/提升 Key 配额。\n\n"
                f"错误摘要：{str(e)[:160]}\n\n"
                "已检索上下文（节选）：\n"
                + (rag_context[:1200] if rag_context else "(empty)")
            )
            await asyncio.to_thread(
                self.repository.add_message,
                conversation_id=conversation_id,
                role="assistant",
                content=response_text,
                product_ids=[selected_product_id] if selected_product_id else None,
            )
            await asyncio.to_thread(
                self.repository.add_agent_log,
                user_id=user_id,
                agent_name="Strategist",
                message="LLM rate-limited during chat; returned context-only reply.",
                log_type="warning",
            )
            return {"response": response_text, "messages": list(messages_in) + [AIMessage(content=response_text)]}
        except TimeoutError:
            response_text = (
                "本次回复超时（可能是模型限流/网络抖动）。我已返回检索到的上下文，建议稍后重试。\n\n"
                "已检索上下文（节选）：\n"
                + (rag_context[:1200] if rag_context else "(empty)")
            )
            await asyncio.to_thread(
                self.repository.add_message,
                conversation_id=conversation_id,
                role="assistant",
                content=response_text,
                product_ids=[selected_product_id] if selected_product_id else None,
            )
            await asyncio.to_thread(
                self.repository.add_agent_log,
                user_id=user_id,
                agent_name="Strategist",
                message="LLM call timed out during chat; returned context-only reply.",
                log_type="warning",
            )
            return {"response": response_text, "messages": list(messages_in) + [AIMessage(content=response_text)]}

        messages = result.get("messages", []) or []
        response_text = ""
        for message in reversed(messages):
            content = getattr(message, "text", None) or getattr(message, "content", "")
            if getattr(message, "type", "") in {"ai", "assistant"} and content:
                response_text = content if isinstance(content, str) else str(content)
                break

        if not response_text:
            response_text = "I have the context loaded, but I couldn't generate a reply just now."

        await asyncio.to_thread(
            self.repository.add_message,
            conversation_id=conversation_id,
            role="assistant",
            content=response_text,
            product_ids=[selected_product_id] if selected_product_id else None,
        )
        await asyncio.to_thread(
            self.repository.add_agent_log,
            user_id=user_id,
            agent_name="Strategist",
            message="Answered a follow-up question using native tools and retrieved context.",
            log_type="info",
        )

        return {"response": response_text, "messages": messages}

    async def _retrieve_memory(self, state: ChatState) -> ChatState:
        user_id = state["user_id"]
        conversation_id = state["conversation_id"]
        scan_session_id = state.get("scan_session_id")
        user_message = state["user_message"]

        scan_context = await asyncio.to_thread(self.repository.get_scan_context, scan_session_id)
        history = await asyncio.to_thread(self.repository.get_conversation_history, conversation_id, 8)
        pinned = await asyncio.to_thread(self.repository.search_memories, user_id=user_id, query="", limit=10)
        pinned = [m for m in pinned if m.pinned]
        keyword = await asyncio.to_thread(
            self.repository.search_memories, user_id=user_id, query=user_message, limit=5
        )
        seen = {m.id for m in pinned}
        memories = pinned + [m for m in keyword if m.id not in seen]
        doc_limit = 3 if settings.ollama_base_url else 6
        doc_context = await asyncio.to_thread(vector_store.search, user_message, doc_limit)

        rag = (
            "SCAN_CONTEXT:\n"
            + safe_json(scan_context)
            + "\n\nPOP_DOCUMENTS (catalog, specs, vendors — Qdrant RAG):\n"
            + (doc_context or "(empty — run `python -m backend.ingest` after Qdrant is up)")
            + "\n\nRECENT_HISTORY:\n"
            + safe_json(history)
            + "\n\nRELEVANT_LONG_TERM_MEMORIES:\n"
            + safe_json([m.model_dump(mode="json") for m in memories])
        )
        system_prompt = (
            "You are the PopSight sourcing copilot for Prince of Peace (PoP), a CPG distributor.\n"
            "Use tools when needed. Save durable memory only for lasting preferences, decisions, or supplier notes.\n\n"
            "Retrieved context (RAG):\n"
            f"{rag}\n"
        )

        convo = await asyncio.to_thread(self.repository.get_conversation, conversation_id)
        prior: list[Any] = []
        for msg in convo.messages[-10:]:
            if msg.role == "user":
                prior.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                prior.append(AIMessage(content=msg.content))

        messages: list[Any] = [SystemMessage(content=system_prompt), *prior, HumanMessage(content=user_message)]
        return {"rag_context": rag, "messages": messages}

    def _build_native_tools(self):
        repo = self.repository

        @tool
        async def get_scan_context(scan_session_id: str | None = None) -> dict:
            """Return scan context including products, trends, and suppliers."""
            return await asyncio.to_thread(repo.get_scan_context, scan_session_id)

        @tool
        async def get_product(product_id: str) -> dict | None:
            """Return a single product record by id."""
            product = await asyncio.to_thread(repo.get_product, product_id)
            return product.model_dump(mode="json") if product else None

        @tool
        async def search_memories(query: str, limit: int = 5, user_id: str = "default-user") -> list[dict]:
            """Search stored long-term memory items for the user."""
            items = await asyncio.to_thread(repo.search_memories, user_id=user_id or "default-user", query=query, limit=limit)
            return [item.model_dump(mode="json") for item in items]

        @tool
        async def get_conversation_history(conversation_id: str, limit: int = 8) -> list[dict]:
            """Return recent conversation messages."""
            return await asyncio.to_thread(repo.get_conversation_history, conversation_id, limit)

        VALID_KINDS = {"user_preference", "product_insight", "supplier_note", "decision"}

        @tool
        async def save_memory(
            title: str,
            content: str,
            kind: str = "decision",
            user_id: str = "default-user",
            conversation_id: str | None = None,
            scan_session_id: str | None = None,
        ) -> dict:
            """Persist a durable memory item. kind: user_preference | product_insight | supplier_note | decision."""
            safe_kind = kind if kind in VALID_KINDS else "decision"
            memory = await asyncio.to_thread(
                repo.add_memory,
                user_id=user_id or "default-user",
                kind=safe_kind,
                title=title,
                content=content,
                source_conversation_id=conversation_id,
                source_scan_session_id=scan_session_id,
                pinned=safe_kind in {"user_preference", "decision"},
            )
            return memory.model_dump(mode="json")

        @tool
        async def delete_memory(memory_id: str) -> str:
            """Delete a saved memory by id (use search_memories first)."""
            deleted = await asyncio.to_thread(repo.delete_memory, memory_id)
            return "Memory deleted." if deleted else "Memory not found."

        return [get_scan_context, get_product, search_memories, get_conversation_history, save_memory, delete_memory]


def ensure_ids(items: list[dict], *, prefix: str) -> list[dict]:
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        copied = dict(item)
        if not copied.get("id"):
            copied["id"] = f"{prefix}-{uuid.uuid4().hex[:10]}"
        out.append(copied)
    return out


def safe_json(value: Any) -> str:
    return json_dump(value)


def json_dump(value: Any) -> str:
    import json

    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(value)
