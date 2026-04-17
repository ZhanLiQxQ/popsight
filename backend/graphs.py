from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from .llm import LLMService
from .repository_factory import RepositoryLike


class ScanState(TypedDict, total=False):
    user_id: str
    topic: str
    analysis: dict[str, Any]
    conversation_id: str
    scan_session_id: str


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


async def inject_runtime_context(request: MCPToolCallRequest, handler):
    runtime = request.runtime
    context = runtime.context

    args = dict(request.args)
    if request.name in {"search_memories", "save_memory"}:
        args.setdefault("user_id", context.user_id)
    if request.name in {"get_conversation_history", "save_memory"}:
        args.setdefault("conversation_id", context.conversation_id)
    if request.name in {"get_scan_context", "save_memory"}:
        args.setdefault("scan_session_id", context.scan_session_id)
    if request.name == "get_product" and context.selected_product_id:
        args.setdefault("product_id", context.selected_product_id)

    return await handler(request.override(args=args))


class GraphService:
    def __init__(self, repository: RepositoryLike, llm_service: LLMService, checkpoints_path: str, root_dir: Path):
        self.repository = repository
        self.llm_service = llm_service
        self.checkpoints_path = checkpoints_path
        self.root_dir = root_dir

    async def scan_topic(self, *, user_id: str, topic: str) -> dict[str, Any]:
        async with AsyncSqliteSaver.from_conn_string(self.checkpoints_path) as checkpointer:
            graph = StateGraph(ScanState)
            graph.add_node("analyze_market", self._analyze_market)
            graph.add_node("persist_scan", self._persist_scan)
            graph.add_edge(START, "analyze_market")
            graph.add_edge("analyze_market", "persist_scan")
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
            graph.add_node("agent_reply", self._agent_reply)
            graph.add_edge(START, "agent_reply")
            graph.add_edge("agent_reply", END)
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

    async def _analyze_market(self, state: ScanState) -> ScanState:
        topic = state["topic"]
        analysis = await self.llm_service.run_grounded_scan(topic)
        return {"analysis": analysis}

    async def _persist_scan(self, state: ScanState) -> ScanState:
        analysis = state["analysis"]
        user_id = state["user_id"]
        topic = state["topic"]

        scan_session = self.repository.create_scan_session(
            user_id=user_id,
            topic=topic,
            summary=analysis.get("summary", f"Scan completed for {topic}."),
            trends=analysis.get("trends", []),
            products=analysis.get("opportunities", []),
            manufacturers=analysis.get("manufacturers", []),
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
            conversation = self.repository.get_conversation(conversation.id)

        self.repository.add_agent_log(
            user_id=user_id,
            agent_name="Strategist",
            message=f'Scan completed for "{topic}".',
            log_type="success",
        )

        for signal in analysis.get("signals", []):
            self.repository.add_agent_log(
                user_id=user_id,
                agent_name=signal.get("agentName", "Strategist"),
                message=signal.get("message", ""),
                log_type=signal.get("type", "info"),
            )

        return {
            "conversation_id": conversation.id,
            "scan_session_id": scan_session.id,
        }

    async def _agent_reply(self, state: ChatState) -> ChatState:
        self.llm_service.ensure_clients()
        user_id = state["user_id"]
        conversation_id = state["conversation_id"]
        scan_session_id = state.get("scan_session_id")
        selected_product_id = state.get("selected_product_id")
        user_message = state["user_message"]

        conversation = self.repository.get_conversation(conversation_id)
        self.repository.add_message(
            conversation_id=conversation_id,
            role="user",
            content=user_message,
            product_ids=[selected_product_id] if selected_product_id else None,
        )
        conversation = self.repository.get_conversation(conversation_id)

        client = MultiServerMCPClient(
            {
                "popsight": {
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": [
                        "-m",
                        "backend.mcp_server",
                        "--db-path",
                        str(self.repository.db_path),
                    ],
                    "cwd": str(self.root_dir),
                }
            },
            tool_interceptors=[inject_runtime_context],
        )
        tools = await client.get_tools()

        system_prompt = (
            "You are the PopSight sourcing copilot. Use tools to inspect the current scan, retrieve "
            "relevant memories, and save durable insights only when the user expresses a lasting "
            "preference, decision, supplier note, or reusable buying rule. Keep answers concise and "
            "commercially useful."
        )

        agent = create_agent(
            model=self.llm_service.chat_model,
            tools=tools,
            system_prompt=system_prompt,
            context_schema=ChatContext,
        )

        history = [{"role": message.role, "content": message.content} for message in conversation.messages[-10:]]
        result = await agent.ainvoke(
            {"messages": history},
            context=ChatContext(
                user_id=user_id,
                conversation_id=conversation_id,
                scan_session_id=scan_session_id,
                selected_product_id=selected_product_id,
            ),
        )

        messages = result.get("messages", [])
        response_text = ""
        for message in reversed(messages):
            content = getattr(message, "text", None) or getattr(message, "content", "")
            if getattr(message, "type", "") == "ai" and content:
                response_text = content if isinstance(content, str) else str(content)
                break

        if not response_text:
            response_text = "I have the context loaded, but I couldn't generate a reply just now."

        self.repository.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=response_text,
            product_ids=[selected_product_id] if selected_product_id else None,
        )
        self.repository.add_agent_log(
            user_id=user_id,
            agent_name="Strategist",
            message="Answered a follow-up question using MCP tools and conversation memory.",
            log_type="info",
        )

        return {"response": response_text}
