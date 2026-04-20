"""Qdrant-backed vector store for PoP document search."""
from __future__ import annotations

from typing import TYPE_CHECKING

from google import genai

from .config import settings

if TYPE_CHECKING:
    from qdrant_client import QdrantClient as QdrantClientType
else:
    QdrantClientType = object  # noqa: UP007

try:
    from qdrant_client import QdrantClient
except ImportError:
    QdrantClient = None  # type: ignore[misc, assignment]

COLLECTION_NAME = "pop_documents"
EMBED_MODEL = "gemini-embedding-001"
VECTOR_DIM = 3072


class VectorStore:
    def __init__(self) -> None:
        self._qdrant: QdrantClientType | None = None
        self._genai: genai.Client | None = None

    def _connect(self) -> bool:
        if QdrantClient is None:
            return False
        if not settings.gemini_api_key:
            return False
        if self._qdrant is None:
            # check_compatibility=False silences the v1.17 client vs v1.14 server warning.
            self._qdrant = QdrantClient(url=settings.qdrant_url, timeout=5, check_compatibility=False)
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
            # qdrant-client >=1.12 replaced .search() with .query_points().
            response = self._qdrant.query_points(
                collection_name=COLLECTION_NAME,
                query=vec,
                limit=limit,
            )
            hits = response.points
            if not hits:
                return ""
            return "\n".join(
                f"[{h.payload.get('source', 'doc')}] {h.payload.get('content', '')}"
                for h in hits
            )
        except Exception as exc:
            print(f"[vector_store] search failed: {exc!r}")
            return ""


vector_store = VectorStore()
