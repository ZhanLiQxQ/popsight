from __future__ import annotations

from .config import Settings
from .repository_postgres import PostgresRepository
from .repository_sqlite import SqliteRepository


RepositoryLike = SqliteRepository | PostgresRepository


def get_repository(settings: Settings) -> RepositoryLike:
    if settings.database_url:
        return PostgresRepository(settings.database_url)
    return SqliteRepository(settings.database_path)

