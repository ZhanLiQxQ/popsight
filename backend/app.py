from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import ROOT_DIR, settings
from .graphs import GraphService
from .llm import LLMService
from .repository_factory import get_repository
from .schemas import (
    BootstrapResponse,
    ChatRequest,
    ChatResponse,
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

app = FastAPI(title="PopSight Agent Intelligence API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


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
    memory = repository.add_memory(
        user_id=request.userId,
        kind=request.kind,
        title=request.title,
        content=request.content,
        source_conversation_id=request.conversationId,
        source_scan_session_id=request.scanSessionId,
        pinned=request.kind in {"user_preference", "decision"},
    )
    repository.add_agent_log(
        user_id=request.userId,
        agent_name="Strategist",
        message=f'Saved long-term memory "{request.title}".',
        log_type="success",
    )
    return SaveMemoryResponse(memory=memory, memories=repository.list_memories(request.userId))
