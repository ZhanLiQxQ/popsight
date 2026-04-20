from __future__ import annotations

import re
from typing import Annotated

import httpx
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import ROOT_DIR, settings
from .graphs import GraphService
from .llm import LLMService
from .macro_cold_start_graph import MacroColdStartRunner
from .pipeline import run_amazon_compliance_pipeline
from .repository_factory import get_repository
from .schemas import (
    AmazonPipelineRequest,
    AmazonPipelineResponse,
    BootstrapResponse,
    ChatRequest,
    ChatResponse,
    CompressedAmazonItem,
    DiscoveryLaneResult,
    MACRO_COLD_START_OPENAPI_EXAMPLES,
    MacroColdStartRequest,
    MacroColdStartResponse,
    SaveMemoryRequest,
    SaveMemoryResponse,
    ScanRequest,
    ScanResponse,
)

repository = get_repository(settings)
repository.initialize()
llm_service = LLMService()
graph_service = GraphService(
    repository=repository,
    llm_service=llm_service,
    checkpoints_path=settings.checkpoints_path,
    root_dir=ROOT_DIR,
)
macro_cold_start_runner = MacroColdStartRunner(repository=repository, llm_service=llm_service)


def _redact_querystring_secrets(message: str) -> str:
    return re.sub(r"api_key=[^&\s]+", "api_key=<redacted>", message, flags=re.I)


app = FastAPI(title="PopSight Agent Intelligence API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    """Bump `amazon_ingest_serp` when SerpAPI Amazon query shape changes (for deploy smoke checks)."""
    return {
        "status": "ok",
        "amazon_ingest_serp": "k+rh+i18n",
    }


def _validate_compressed_rows(rows: list) -> list[CompressedAmazonItem]:
    out: list[CompressedAmazonItem] = []
    for row in rows:
        if isinstance(row, dict):
            try:
                out.append(CompressedAmazonItem.model_validate(row))
            except Exception:
                continue
    return out


def _lane_dict_to_result(lane: dict) -> DiscoveryLaneResult:
    return DiscoveryLaneResult(
        categoryId=str(lane.get("category_id") or ""),
        categoryLabel=str(lane.get("category_label") or ""),
        trendsSeed=str(lane.get("trends_seed") or ""),
        googleTrendsSignals=list(lane.get("google_trends_signals") or []),
        amazonSearchTerms=list(lane.get("amazon_search_terms") or []),
        rawAmazonData=list(lane.get("raw_amazon_data") or []),
        compressedItems=_validate_compressed_rows(lane.get("compressed_items") or []),
    )


@app.post("/api/pipeline/macro-cold-start", response_model=MacroColdStartResponse)
async def macro_cold_start_pipeline(
    request: Annotated[MacroColdStartRequest, Body(openapi_examples=MACRO_COLD_START_OPENAPI_EXAMPLES)],
) -> MacroColdStartResponse:
    """
    LangGraph discovery: per lane — Google Trends → MacroScout → Amazon Serp → FDA/GLiNER (Node 0–3),
    then rank → supply → summary (Node 4–6).
    """
    llm_service.ensure_clients()
    if not settings.serpapi_api_key.strip():
        raise HTTPException(status_code=500, detail="Missing SERPAPI_API_KEY.")

    try:
        lane_ids = [e.value for e in request.discoveryLaneIds] if request.discoveryLaneIds else None
        state = await macro_cold_start_runner.run(
            user_id=request.userId,
            google_trends_geo=request.googleTrendsGeo.strip() or "US",
            amazon_domain=request.amazonDomain.strip() or "amazon.com",
            discovery_lane_ids=lane_ids,
        )
    except httpx.HTTPError as exc:
        safe = _redact_querystring_secrets(str(exc))
        raise HTTPException(status_code=502, detail=f"Upstream HTTP error: {safe}") from exc

    lane_payloads = [_lane_dict_to_result(ln) for ln in (state.get("lanes") or []) if isinstance(ln, dict)]

    return MacroColdStartResponse(
        lanes=lane_payloads,
        googleTrendsSignals=list(state.get("google_trends_signals") or []),
        amazonSearchTerms=list(state.get("amazon_search_terms") or []),
        rawAmazonData=list(state.get("raw_amazon_data") or []),
        compressedItems=_validate_compressed_rows(state.get("compressed_items") or []),
        rankedProductList=list(state.get("ranked_product_list") or []),
        finalActionableList=list(state.get("final_actionable_list") or []),
        executiveSummary=str(state.get("executive_summary") or ""),
        discoveryAborted=bool(state.get("discovery_pipeline_aborted")),
        discoveryAbortReason=(
            (str(state.get("discovery_abort_reason") or "").strip() or None)
            if state.get("discovery_pipeline_aborted")
            else None
        ),
    )


@app.post("/api/pipeline/amazon-ingest", response_model=AmazonPipelineResponse)
async def amazon_ingest_pipeline(request: AmazonPipelineRequest) -> AmazonPipelineResponse:
    """
    Standalone Amazon Serp → compliance → compression (+ optional GLiNER). Not part of the discovery graph.
    """
    if not settings.serpapi_api_key.strip():
        raise HTTPException(status_code=500, detail="Missing SERPAPI_API_KEY.")

    try:
        result = await run_amazon_compliance_pipeline(
            search_term=request.query.strip(),
            api_key=settings.serpapi_api_key.strip(),
            amazon_domain=request.amazon_domain.strip() or "amazon.com",
            max_products=request.max_products,
            include_raw_preview=request.include_raw_preview,
            category_preset=request.category_preset,
            category_node=request.category_node.strip() if request.category_node else None,
            gliner_enabled=settings.gliner_enabled,
            gliner_model_id=settings.gliner_model_id,
            gliner_threshold=settings.gliner_threshold,
            gliner_max_input_chars=settings.gliner_max_input_chars,
            gliner_batch_size=settings.gliner_batch_size,
            gliner_console_samples=settings.gliner_console_samples,
        )
    except httpx.HTTPError as exc:
        safe = _redact_querystring_secrets(str(exc))
        raise HTTPException(status_code=502, detail=f"SerpAPI HTTP error: {safe}") from exc

    err = result.pop("serpapi_error", None)
    if err:
        raise HTTPException(status_code=502, detail=err)

    return AmazonPipelineResponse.model_validate(result)


@app.get("/api/bootstrap", response_model=BootstrapResponse)
async def bootstrap(user_id: str = "default-user") -> BootstrapResponse:
    macros = repository.list_macros(user_id)
    if not macros and settings.auto_bootstrap_macros and settings.gemini_api_key:
        discovered = await llm_service.get_macro_discoveries()
        repository.replace_macros(user_id, discovered)
        macros = repository.list_macros(user_id)

    return BootstrapResponse(
        conversations=repository.list_conversations(user_id),
        memories=repository.list_memories(user_id),
        scanSessions=repository.list_scan_sessions(user_id),
        agentLogs=repository.get_recent_logs(user_id),
        macros=macros,
    )


@app.post("/api/scan", response_model=ScanResponse)
async def scan_market(request: ScanRequest) -> ScanResponse:
    if not settings.gemini_api_key and not settings.allow_demo_mode_without_llm_key:
        raise HTTPException(status_code=500, detail="Missing GEMINI_API_KEY or GOOGLE_API_KEY.")

    await graph_service.scan_topic(user_id=request.userId, topic=request.topic)
    conversation = repository.list_conversations(request.userId, limit=1)[0]
    if not conversation.scanSessionId:
        raise HTTPException(status_code=500, detail="Scan completed without a scan session.")
    scan_session = repository.get_scan_session(conversation.scanSessionId)
    return ScanResponse(
        conversation=conversation,
        scanSession=scan_session,
        agentLogs=repository.get_recent_logs(request.userId, limit=40),
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    conversation_id = request.conversationId
    topic = "Ad hoc sourcing thread"
    if request.scanSessionId:
        topic = repository.get_scan_session(request.scanSessionId).topic

    if conversation_id:
        try:
            repository.get_conversation(conversation_id)
        except KeyError:
            conversation = repository.upsert_conversation(
                user_id=request.userId,
                topic=topic,
                title=topic,
                scan_session_id=request.scanSessionId,
                conversation_id=conversation_id,
            )
            conversation_id = conversation.id
    else:
        conversation = repository.upsert_conversation(
            user_id=request.userId,
            topic=topic,
            title=topic,
            scan_session_id=request.scanSessionId,
        )
        conversation_id = conversation.id

    await graph_service.chat(
        user_id=request.userId,
        conversation_id=conversation_id,
        scan_session_id=request.scanSessionId,
        user_message=request.message,
        selected_product_id=request.selectedProductId,
    )

    return ChatResponse(
        conversation=repository.get_conversation(conversation_id),
        memories=repository.list_memories(request.userId),
        agentLogs=repository.get_recent_logs(request.userId, limit=40),
    )


@app.post("/api/memory", response_model=SaveMemoryResponse)
async def save_memory(request: SaveMemoryRequest) -> SaveMemoryResponse:
    pinned = (
        request.pinned
        if request.pinned is not None
        else request.kind in {"user_preference", "decision", "product_insight"}
    )
    memory = repository.add_memory(
        user_id=request.userId,
        kind=request.kind,
        title=request.title,
        content=request.content,
        source_conversation_id=request.conversationId,
        source_scan_session_id=request.scanSessionId,
        pinned=pinned,
    )
    repository.add_agent_log(
        user_id=request.userId,
        agent_name="Strategist",
        message=f'Saved long-term memory "{request.title}".',
        log_type="success",
    )
    return SaveMemoryResponse(memory=memory, memories=repository.list_memories(request.userId))


@app.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: str, userId: str = "default-user") -> dict:
    deleted = repository.delete_memory(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {
        "deleted": True,
        "memories": [m.model_dump(mode="json") for m in repository.list_memories(userId)],
    }
