from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
