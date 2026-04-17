from __future__ import annotations

import argparse

from mcp.server.fastmcp import FastMCP

from .repository import Repository


def create_mcp_server(db_path_or_url: str) -> FastMCP:
    repository = Repository(db_path_or_url)
    repository.initialize()
    mcp = FastMCP("PopSight MCP", json_response=True)

    @mcp.tool()
    def get_scan_context(scan_session_id: str | None = None) -> dict:
        """Return the current scan context including products, trends, and suppliers."""
        return repository.get_scan_context(scan_session_id)

    @mcp.tool()
    def get_product(product_id: str) -> dict | None:
        """Return a single product record by id."""
        product = repository.get_product(product_id)
        return product.model_dump(mode="json") if product else None

    @mcp.tool()
    def search_memories(user_id: str, query: str, limit: int = 5) -> list[dict]:
        """Search stored long-term memory items for the user."""
        return [item.model_dump(mode="json") for item in repository.search_memories(user_id=user_id, query=query, limit=limit)]

    @mcp.tool()
    def get_conversation_history(conversation_id: str, limit: int = 8) -> list[dict]:
        """Return recent conversation messages."""
        return repository.get_conversation_history(conversation_id, limit=limit)

    @mcp.tool()
    def save_memory(
        user_id: str,
        kind: str,
        title: str,
        content: str,
        conversation_id: str | None = None,
        scan_session_id: str | None = None,
    ) -> dict:
        """Persist a durable memory item for future conversations."""
        memory = repository.add_memory(
            user_id=user_id,
            kind=kind,
            title=title,
            content=content,
            source_conversation_id=conversation_id,
            source_scan_session_id=scan_session_id,
            pinned=kind in {"user_preference", "decision"},
        )
        return memory.model_dump(mode="json")

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", required=True, help="SQLite path or Postgres URL")
    args = parser.parse_args()

    server = create_mcp_server(args.db_path)
    server.run()


if __name__ == "__main__":
    main()
