"""Qdrant-backed vector store for PoP document search."""
from __future__ import annotations

from google import genai
from qdrant_client import QdrantClient

from .config import settings

COLLECTION_NAME = "pop_documents"
EMBED_MODEL = "gemini-embedding-001"
VECTOR_DIM = 3072


class VectorStore:
    def __init__(self) -> None:
        self._qdrant: QdrantClient | None = None
        self._genai: genai.Client | None = None

    def _connect(self) -> bool:
        if not settings.gemini_api_key:
            return False
        if self._qdrant is None:
            self._qdrant = QdrantClient(url=settings.qdrant_url, timeout=5)
        if self._genai is None:
            self._genai = genai.Client(api_key=settings.gemini_api_key)
        return True

    def _embed(self, text: str) -> list[float]:
        result = self._genai.models.embed_content(model=EMBED_MODEL, contents=text)
        return result.embeddings[0].values

    def search(self, query: str, limit: int = 5) -> str:
        """Return formatted context string; empty string if unavailable."""
        try:
            if not self._connect():
                return ""
            vec = self._embed(query)
            hits = self._qdrant.search(
                collection_name=COLLECTION_NAME,
                query_vector=vec,
                limit=limit,
            )
            if not hits:
                return ""
            return "\n".join(
                f"[{h.payload.get('source', 'doc')}] {h.payload.get('content', '')}"
                for h in hits
            )
        except Exception:
            return ""


vector_store = VectorStore()
