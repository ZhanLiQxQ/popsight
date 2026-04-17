from __future__ import annotations

from pathlib import Path
from typing import Any

from .repository_postgres import PostgresRepository
from .repository_sqlite import SqliteRepository


class Repository:
    """
    Backwards-compatible facade.

    Historically this project used SQLite only and accepted `db_path`.
    We now support Postgres via `POPSIGHT_DATABASE_URL`, but keep this wrapper so
    older imports keep working (notably the MCP server).
    """

    def __init__(self, db_path: str | Path | None = None, *, database_url: str | None = None):
        url = (database_url or "").strip()
        if not url and isinstance(db_path, str) and db_path.strip().lower().startswith("postgres"):
            url = db_path.strip()

        if url:
            self._impl: Any = PostgresRepository(url)
        else:
            path = db_path if isinstance(db_path, Path) else Path(str(db_path or "data/popsight.db"))
            self._impl = SqliteRepository(path)

    def __getattr__(self, name: str):
        return getattr(self._impl, name)

