from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Env:
    # Legacy sources remain optional for users who already configured them.
    metals_dev_api_key: str = os.getenv("METALS_DEV_API_KEY", "")
    goldapi_key: str = os.getenv("GOLDAPI_KEY", "")  # legacy goldapi.io key
    twelve_data_api_key: str = os.getenv("TWELVE_DATA_API_KEY", "")

    # Free multi-source architecture.
    xaus_enabled: bool = _bool("XAUS_ENABLED", True)
    gold_api_com_enabled: bool = _bool("GOLD_API_COM_ENABLED", True)
    goldapi_dev_key: str = os.getenv("GOLDAPI_DEV_KEY", "")
    goldprice_enabled: bool = _bool("GOLDPRICE_ENABLED", True)
    goldprice_api_key: str = os.getenv("GOLDPRICE_API_KEY", "")
    frankfurter_enabled: bool = _bool("FRANKFURTER_ENABLED", True)

    poll_seconds: int = _int("POLL_SECONDS", 60)
    request_timeout: float = _float("REQUEST_TIMEOUT_SECONDS", 12.0)
    database_path: str = os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "data" / "gold_tracker.db"))
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    kalyan_url: str = os.getenv("KALYAN_RATE_URL", "https://store.kalyanjewellers.net/gold-rate/india/en")
    ibja_url: str = os.getenv("IBJA_RATE_URL", "https://ibjarates.com/")
    default_import_duty_pct: float = _float("DEFAULT_IMPORT_DUTY_PCT", 15.0)


ENV = Env()
