from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .schemas import (
    AgentLogPayload,
    ChatMessagePayload,
    ConversationPayload,
    MacroSuggestionPayload,
    ManufacturerPayload,
    MemoryPayload,
    ProductPayload,
    ScanSessionPayload,
    TrendPayload,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def make_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def normalize_text(value: Any, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def normalize_trend_sentiment(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "positive" in text or "bull" in text or "strong" in text:
        return "Positive"
    if "mix" in text or "balanced" in text:
        return "Mixed"
    return "Neutral"


def normalize_product_velocity(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "explosive" in text or "surging" in text or "breakout" in text:
        return "Explosive"
    if "rising" in text or "growing" in text or "up" in text:
        return "Rising"
    return "Stable"


def normalize_distribution_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "parallel" in text:
        return "Parallel Import"
    if "not in us" in text or "absent" in text or "unavailable" in text:
        return "Not in US"
    return "Under-distributed"


def normalize_capacity(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "high" in text or "large" in text:
        return "High"
    if "low" in text or "small" in text:
        return "Low"
    return "Medium"


def normalize_contact_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "partner" in text:
        return "Partner"
    if "contact" in text or "reached" in text:
        return "Contacted"
    return "Identified"


def normalize_agent_log_type(value: Any) -> str:
    """
    AgentLogPayload.type is a strict enum ("info"|"success"|"warning"|"error").
    Older DB rows (or callers) may store human labels like "Supply Chain Alert".
    We coerce those into the closest enum to keep the API stable.
    """

    text = str(value or "").strip()
    lowered = text.lower()
    allowed = {"info", "success", "warning", "error"}
    if lowered in allowed:
        return lowered
    if "error" in lowered or "fail" in lowered or "exception" in lowered:
        return "error"
    if "warn" in lowered or "alert" in lowered or "risk" in lowered:
        return "warning"
    if "success" in lowered or "ok" == lowered or "done" in lowered or "complete" in lowered:
        return "success"
    return "info"


def normalize_specialization(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    if value is None:
        return []

    text = str(value).strip()
    if not text:
        return []

    separators = ["\n", ";", "|", ",", " / "]
    parts = [text]
    for separator in separators:
        if separator in text:
            parts = [item.strip() for item in text.split(separator)]
            break

    cleaned = [item for item in parts if item]
    return cleaned or [text]


class SqliteRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(exist_ok=True)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS scan_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trends (
                    id TEXT PRIMARY KEY,
                    scan_session_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    category TEXT NOT NULL,
                    growth TEXT NOT NULL,
                    sentiment TEXT NOT NULL,
                    top_keywords_json TEXT NOT NULL,
                    FOREIGN KEY(scan_session_id) REFERENCES scan_sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS products (
                    id TEXT PRIMARY KEY,
                    scan_session_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    brand TEXT NOT NULL,
                    category TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    traction_score INTEGER NOT NULL,
                    velocity TEXT NOT NULL,
                    distribution_status TEXT NOT NULL,
                    price_point TEXT NOT NULL,
                    description TEXT NOT NULL,
                    image TEXT,
                    FOREIGN KEY(scan_session_id) REFERENCES scan_sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS manufacturers (
                    id TEXT PRIMARY KEY,
                    scan_session_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    location TEXT NOT NULL,
                    specialization_json TEXT NOT NULL,
                    capacity TEXT NOT NULL,
                    contact_status TEXT NOT NULL,
                    FOREIGN KEY(scan_session_id) REFERENCES scan_sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    scan_session_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    product_ids_json TEXT,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS memory_items (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_conversation_id TEXT,
                    source_scan_session_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    pinned INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS agent_logs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    type TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS macro_suggestions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    region TEXT NOT NULL,
                    growth_indicator TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def replace_macros(self, user_id: str, macros: list[MacroSuggestionPayload]) -> None:
        now = utc_now().isoformat()
        with self.connect() as conn:
            conn.execute("DELETE FROM macro_suggestions WHERE user_id = ?", (user_id,))
            conn.executemany(
                """
                INSERT INTO macro_suggestions (id, user_id, category, reason, region, growth_indicator, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        make_id("macro"),
                        user_id,
                        macro.category,
                        macro.reason,
                        macro.region,
                        macro.growthIndicator,
                        now,
                    )
                    for macro in macros
                ],
            )

    def list_macros(self, user_id: str, limit: int = 6) -> list[MacroSuggestionPayload]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT category, reason, region, growth_indicator
                FROM macro_suggestions
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()

        return [
            MacroSuggestionPayload(
                category=row["category"],
                reason=row["reason"],
                region=row["region"],
                growthIndicator=row["growth_indicator"],
            )
            for row in rows
        ]

    def upsert_conversation(
        self,
        *,
        user_id: str,
        topic: str,
        title: str | None = None,
        scan_session_id: str | None = None,
        conversation_id: str | None = None,
    ) -> ConversationPayload:
        now = utc_now().isoformat()
        with self.connect() as conn:
            if conversation_id:
                row = conn.execute(
                    "SELECT * FROM conversations WHERE id = ?",
                    (conversation_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM conversations
                    WHERE user_id = ? AND topic = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (user_id, topic),
                ).fetchone()

            if row:
                conversation_id = row["id"]
                updated_title = normalize_text(title, row["title"])
                updated_topic = normalize_text(topic, row["topic"])
                updated_scan_session = scan_session_id or row["scan_session_id"]
                conn.execute(
                    """
                    UPDATE conversations
                    SET title = ?, topic = ?, scan_session_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (updated_title, updated_topic, updated_scan_session, now, conversation_id),
                )
            else:
                conversation_id = conversation_id or make_id("convo")
                conn.execute(
                    """
                    INSERT INTO conversations (id, user_id, title, topic, scan_session_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (conversation_id, user_id, normalize_text(title, topic), topic, scan_session_id, now, now),
                )

        return self.get_conversation(conversation_id)

    def add_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        product_ids: list[str] | None = None,
        timestamp: datetime | None = None,
    ) -> ChatMessagePayload:
        message_id = make_id("msg")
        ts = (timestamp or utc_now()).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (id, conversation_id, role, content, timestamp, product_ids_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, conversation_id, role, content, ts, json.dumps(product_ids or [])),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (ts, conversation_id),
            )

        return ChatMessagePayload(
            id=message_id,
            role=role,  # type: ignore[arg-type]
            content=content,
            timestamp=datetime.fromisoformat(ts),
            productIds=product_ids or None,
        )

    def create_scan_session(
        self,
        *,
        user_id: str,
        topic: str,
        summary: str,
        trends: list[dict[str, Any]],
        products: list[dict[str, Any]],
        manufacturers: list[dict[str, Any]],
    ) -> ScanSessionPayload:
        scan_session_id = make_id("scan")
        now = utc_now().isoformat()
        summary = normalize_text(summary, "No summary available.")

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO scan_sessions (id, user_id, topic, summary, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (scan_session_id, user_id, topic, summary, now),
            )

            conn.executemany(
                """
                INSERT INTO trends (id, scan_session_id, topic, category, growth, sentiment, top_keywords_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        make_id("trend"),
                        scan_session_id,
                        normalize_text(item.get("topic"), topic),
                        normalize_text(item.get("category"), "Other"),
                        normalize_text(item.get("growth"), "Unknown"),
                        normalize_trend_sentiment(item.get("sentiment")),
                        json.dumps(item.get("topKeywords", []) or []),
                    )
                    for item in trends
                ],
            )

            conn.executemany(
                """
                INSERT INTO products (
                    id, scan_session_id, name, brand, category, origin,
                    traction_score, velocity, distribution_status, price_point, description, image
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        make_id("product"),
                        scan_session_id,
                        normalize_text(item.get("name"), "Unknown product"),
                        normalize_text(item.get("brand"), "Unknown brand"),
                        normalize_text(item.get("category"), "Other"),
                        normalize_text(item.get("origin"), "Unknown"),
                        int(item.get("tractionScore") or 0),
                        normalize_product_velocity(item.get("velocity")),
                        normalize_distribution_status(item.get("distributionStatus")),
                        normalize_text(item.get("pricePoint"), "Unknown"),
                        normalize_text(item.get("description"), "No description available."),
                        item.get("image"),
                    )
                    for item in products
                ],
            )

            conn.executemany(
                """
                INSERT INTO manufacturers (
                    id, scan_session_id, name, location, specialization_json, capacity, contact_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        make_id("manufacturer"),
                        scan_session_id,
                        normalize_text(item.get("name"), "Unknown supplier"),
                        normalize_text(item.get("location"), "Unknown location"),
                        json.dumps(normalize_specialization(item.get("specialization", []))),
                        normalize_capacity(item.get("capacity", "Medium")),
                        normalize_contact_status(item.get("contactStatus", "Identified")),
                    )
                    for item in manufacturers
                ],
            )

        return self.get_scan_session(scan_session_id)

    def add_agent_log(
        self,
        *,
        user_id: str,
        agent_name: str,
        message: str,
        log_type: str = "info",
    ) -> AgentLogPayload:
        log_id = make_id("log")
        timestamp = utc_now().isoformat()
        normalized_type = normalize_agent_log_type(log_type)
        stored_message = message
        if normalized_type != str(log_type or "").strip().lower():
            original_label = str(log_type or "").strip()
            if original_label:
                stored_message = f"[{original_label}] {message}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_logs (id, user_id, agent_name, message, timestamp, type)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (log_id, user_id, agent_name, stored_message, timestamp, normalized_type),
            )

        return AgentLogPayload(
            id=log_id,
            agentName=agent_name,
            message=stored_message,
            timestamp=datetime.fromisoformat(timestamp),
            type=normalized_type,  # type: ignore[arg-type]
        )

    def add_memory(
        self,
        *,
        user_id: str,
        kind: str,
        title: str,
        content: str,
        source_conversation_id: str | None = None,
        source_scan_session_id: str | None = None,
        pinned: bool = False,
    ) -> MemoryPayload:
        memory_id = make_id("memory")
        now = utc_now().isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_items (
                    id, user_id, kind, title, content, source_conversation_id, source_scan_session_id,
                    created_at, updated_at, pinned
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    user_id,
                    kind,
                    title,
                    content,
                    source_conversation_id,
                    source_scan_session_id,
                    now,
                    now,
                    1 if pinned else 0,
                ),
            )

        return self.get_memory(memory_id)

    def search_memories(self, *, user_id: str, query: str, limit: int = 5) -> list[MemoryPayload]:
        search_value = f"%{query.strip()}%"
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memory_items
                WHERE user_id = ? AND (title LIKE ? OR content LIKE ?)
                ORDER BY pinned DESC, updated_at DESC
                LIMIT ?
                """,
                (user_id, search_value, search_value, limit),
            ).fetchall()

        return [self._memory_from_row(row) for row in rows]

    def delete_memory(self, memory_id: str) -> bool:
        with self.connect() as conn:
            conn.execute("DELETE FROM memory_items WHERE id = ?", (memory_id,))
            return conn.total_changes > 0

    def get_recent_logs(self, user_id: str, limit: int = 80) -> list[AgentLogPayload]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM agent_logs
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()

        return [
            AgentLogPayload(
                id=row["id"],
                agentName=row["agent_name"],
                message=(
                    f"[{row['type']}] {row['message']}"
                    if str(row["type"] or "").strip().lower() not in {"info", "success", "warning", "error"}
                    else row["message"]
                ),
                timestamp=datetime.fromisoformat(row["timestamp"]),
                type=normalize_agent_log_type(row["type"]),  # type: ignore[arg-type]
            )
            for row in rows
        ]

    def list_conversations(self, user_id: str, limit: int = 20) -> list[ConversationPayload]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id FROM conversations
                WHERE user_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()

        return [self.get_conversation(row["id"]) for row in rows]

    def list_scan_sessions(self, user_id: str, limit: int = 20) -> list[ScanSessionPayload]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id FROM scan_sessions
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()

        return [self.get_scan_session(row["id"]) for row in rows]

    def list_memories(self, user_id: str, limit: int = 30) -> list[MemoryPayload]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memory_items
                WHERE user_id = ?
                ORDER BY pinned DESC, updated_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()

        return [self._memory_from_row(row) for row in rows]

    def get_conversation(self, conversation_id: str) -> ConversationPayload:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Conversation not found: {conversation_id}")

            message_rows = conn.execute(
                """
                SELECT * FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp ASC
                """,
                (conversation_id,),
            ).fetchall()

        return ConversationPayload(
            id=row["id"],
            title=row["title"],
            topic=row["topic"],
            scanSessionId=row["scan_session_id"],
            createdAt=datetime.fromisoformat(row["created_at"]),
            updatedAt=datetime.fromisoformat(row["updated_at"]),
            messages=[
                ChatMessagePayload(
                    id=message["id"],
                    role=message["role"],  # type: ignore[arg-type]
                    content=message["content"],
                    timestamp=datetime.fromisoformat(message["timestamp"]),
                    productIds=json.loads(message["product_ids_json"] or "[]") or None,
                )
                for message in message_rows
            ],
        )

    def get_scan_session(self, scan_session_id: str) -> ScanSessionPayload:
        with self.connect() as conn:
            session_row = conn.execute(
                "SELECT * FROM scan_sessions WHERE id = ?",
                (scan_session_id,),
            ).fetchone()
            if session_row is None:
                raise KeyError(f"Scan session not found: {scan_session_id}")

            trend_rows = conn.execute(
                """
                SELECT * FROM trends
                WHERE scan_session_id = ?
                ORDER BY rowid ASC
                """,
                (scan_session_id,),
            ).fetchall()

            product_rows = conn.execute(
                """
                SELECT * FROM products
                WHERE scan_session_id = ?
                ORDER BY traction_score DESC
                """,
                (scan_session_id,),
            ).fetchall()

            manufacturer_rows = conn.execute(
                """
                SELECT * FROM manufacturers
                WHERE scan_session_id = ?
                ORDER BY name ASC
                """,
                (scan_session_id,),
            ).fetchall()

        return ScanSessionPayload(
            id=session_row["id"],
            topic=session_row["topic"],
            createdAt=datetime.fromisoformat(session_row["created_at"]),
            summary=session_row["summary"],
            trends=[
                TrendPayload(
                    id=row["id"],
                    topic=row["topic"],
                    category=row["category"],
                    growth=row["growth"],
                    sentiment=row["sentiment"],  # type: ignore[arg-type]
                    topKeywords=json.loads(row["top_keywords_json"] or "[]"),
                )
                for row in trend_rows
            ],
            opportunities=[
                ProductPayload(
                    id=row["id"],
                    name=row["name"],
                    brand=row["brand"],
                    category=row["category"],
                    origin=row["origin"],
                    tractionScore=int(row["traction_score"]),
                    velocity=row["velocity"],  # type: ignore[arg-type]
                    distributionStatus=row["distribution_status"],  # type: ignore[arg-type]
                    pricePoint=row["price_point"],
                    description=row["description"],
                    image=row["image"],
                )
                for row in product_rows
            ],
            manufacturers=[
                ManufacturerPayload(
                    id=row["id"],
                    name=row["name"],
                    location=row["location"],
                    specialization=json.loads(row["specialization_json"] or "[]"),
                    capacity=row["capacity"],  # type: ignore[arg-type]
                    contactStatus=row["contact_status"],  # type: ignore[arg-type]
                )
                for row in manufacturer_rows
            ],
        )

    def get_memory(self, memory_id: str) -> MemoryPayload:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_items WHERE id = ?",
                (memory_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Memory not found: {memory_id}")
        return self._memory_from_row(row)

    def get_product(self, product_id: str) -> ProductPayload | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE id = ?",
                (product_id,),
            ).fetchone()
            if row is None:
                return None

        return ProductPayload(
            id=row["id"],
            name=row["name"],
            brand=row["brand"],
            category=row["category"],
            origin=row["origin"],
            tractionScore=int(row["traction_score"]),
            velocity=row["velocity"],  # type: ignore[arg-type]
            distributionStatus=row["distribution_status"],  # type: ignore[arg-type]
            pricePoint=row["price_point"],
            description=row["description"],
            image=row["image"],
        )

    def get_scan_context(self, scan_session_id: str | None) -> dict[str, Any]:
        if not scan_session_id:
            return {}
        try:
            session = self.get_scan_session(scan_session_id)
        except KeyError:
            return {}

        return {
            "scanSessionId": session.id,
            "topic": session.topic,
            "summary": session.summary,
            "trends": [trend.model_dump() for trend in session.trends],
            "opportunities": [product.model_dump() for product in session.opportunities],
            "manufacturers": [manufacturer.model_dump() for manufacturer in session.manufacturers],
        }

    def get_conversation_history(self, conversation_id: str, limit: int = 8) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, timestamp
                FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()

        return [
            {"role": row["role"], "content": row["content"], "timestamp": row["timestamp"]}
            for row in reversed(rows)
        ]

    def _memory_from_row(self, row: sqlite3.Row) -> MemoryPayload:
        return MemoryPayload(
            id=row["id"],
            kind=row["kind"],  # type: ignore[arg-type]
            title=row["title"],
            content=row["content"],
            pinned=bool(row["pinned"]),
            createdAt=datetime.fromisoformat(row["created_at"]),
            updatedAt=datetime.fromisoformat(row["updated_at"]),
            sourceConversationId=row["source_conversation_id"],
            sourceScanSessionId=row["source_scan_session_id"],
        )

