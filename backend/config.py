from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
    app_url: str = os.getenv("APP_URL", "http://localhost:8000")
    database_url: str = os.getenv("POPSIGHT_DATABASE_URL", "")
    database_path: Path = Path(os.getenv("POPSIGHT_DB_PATH", str(DATA_DIR / "popsight.db")))
    checkpoints_path: str = os.getenv(
        "POPSIGHT_CHECKPOINT_DB_PATH",
        str(DATA_DIR / "langgraph-checkpoints.sqlite"),
    )
    scan_model: str = os.getenv("POPSIGHT_SCAN_MODEL", "gemini-2.5-flash")
    chat_model: str = os.getenv("POPSIGHT_CHAT_MODEL", "gemini-2.5-flash")
    auto_bootstrap_macros: bool = os.getenv("POPSIGHT_AUTO_BOOTSTRAP_MACROS", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    allow_demo_mode_without_llm_key: bool = os.getenv("POPSIGHT_ALLOW_DEMO_MODE", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    qdrant_url: str = os.getenv("POPSIGHT_QDRANT_URL", "http://localhost:6333")
    qdrant_api_key: str = os.getenv("POPSIGHT_QDRANT_API_KEY", "")


settings = Settings()
