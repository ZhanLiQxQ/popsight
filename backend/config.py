from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

load_dotenv(ROOT_DIR / ".env")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(str(raw).strip())
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


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
    auto_bootstrap_macros: bool = os.getenv("POPSIGHT_AUTO_BOOTSTRAP_MACROS", "true").strip().lower() in {
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
    serpapi_api_key: str = os.getenv("SERPAPI_API_KEY", "")
    gliner_enabled: bool = os.getenv("POPSIGHT_GLINER_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    gliner_model_id: str = os.getenv("POPSIGHT_GLINER_MODEL_ID", "urchade/gliner_small-v2.1")
    gliner_threshold: float = _env_float("POPSIGHT_GLINER_THRESHOLD", 0.35)
    gliner_max_input_chars: int = _env_int("POPSIGHT_GLINER_MAX_INPUT_CHARS", 1500)
    gliner_batch_size: int = _env_int("POPSIGHT_GLINER_BATCH_SIZE", 8)
    gliner_console_samples: int = _env_int("POPSIGHT_GLINER_CONSOLE_SAMPLES", 3)


settings = Settings()
