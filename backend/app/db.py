from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import ENV

DEFAULT_SETTINGS: dict[str, float] = {
    "import_duty_pct": ENV.default_import_duty_pct,
    "domestic_premium_pct": 0.50,
    "local_cost_inr_per_10g": 0.0,
    "gst_pct": 3.0,
    "coin_premium_pct": 0.75,
    "coin_fixed_fee_inr": 0.0,
    "coin_weight_g": 10.0,
    "kalyan_max_premium_pct": 0.75,
    "watch_discount_pct": 0.50,
    "alert_move_pct": 0.75,
}


def _connect() -> sqlite3.Connection:
    path = Path(ENV.database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            captured_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )""")
        conn.execute("""CREATE INDEX IF NOT EXISTS idx_snapshots_captured_at
            ON snapshots(captured_at)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS manual_overrides (
            field TEXT PRIMARY KEY,
            value REAL NOT NULL,
            source_label TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS retailer_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            retailer_id TEXT NOT NULL,
            city TEXT NOT NULL,
            gold_22k_per_g REAL,
            gold_24k_per_g REAL,
            coin_10g_total REAL,
            making_charge_pct REAL,
            source_label TEXT NOT NULL,
            source_url TEXT,
            notes TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(retailer_id, city)
        )""")
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO app_settings(key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )


def save_snapshot(payload: dict[str, Any]) -> None:
    captured_at = payload.get("captured_at") or datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO snapshots(captured_at, payload) VALUES (?, ?)",
            (captured_at, json.dumps(payload, separators=(",", ":"))),
        )
        cutoff = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
        conn.execute("DELETE FROM snapshots WHERE captured_at < ?", (cutoff,))


def latest_snapshot() -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT payload FROM snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return json.loads(row["payload"]) if row else None


def history(hours: int = 24) -> list[dict[str, Any]]:
    start = (datetime.now(timezone.utc) - timedelta(hours=max(1, min(hours, 24 * 45)))).isoformat()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT payload FROM snapshots WHERE captured_at >= ? ORDER BY id ASC",
            (start,),
        ).fetchall()
    return [json.loads(row["payload"]) for row in rows]


def get_settings() -> dict[str, float]:
    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    result = DEFAULT_SETTINGS.copy()
    for row in rows:
        try:
            result[row["key"]] = float(json.loads(row["value"]))
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
    return result


def update_settings(values: dict[str, float]) -> dict[str, float]:
    allowed = set(DEFAULT_SETTINGS)
    with _connect() as conn:
        for key, value in values.items():
            if key in allowed:
                conn.execute(
                    "INSERT INTO app_settings(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, json.dumps(float(value))),
                )
    return get_settings()


def get_overrides() -> dict[str, dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM manual_overrides").fetchall()
    return {
        row["field"]: {
            "value": float(row["value"]),
            "source": row["source_label"],
            "timestamp": row["updated_at"],
        }
        for row in rows
    }


def set_override(field: str, value: float, source_label: str) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO manual_overrides(field, value, source_label, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(field) DO UPDATE SET value=excluded.value, source_label=excluded.source_label, updated_at=excluded.updated_at",
            (field, float(value), source_label, timestamp),
        )
    return {"value": float(value), "source": source_label, "timestamp": timestamp}


def delete_override(field: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM manual_overrides WHERE field = ?", (field,))
    return cur.rowcount > 0


def get_retailer_quotes(city: str = "Pune") -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM retailer_quotes WHERE lower(city)=lower(?) ORDER BY retailer_id",
            (city,),
        ).fetchall()
    return [{
        "retailer_id": row["retailer_id"],
        "city": row["city"],
        "gold_22k_per_g": row["gold_22k_per_g"],
        "gold_24k_per_g": row["gold_24k_per_g"],
        "coin_10g_total": row["coin_10g_total"],
        "making_charge_pct": row["making_charge_pct"],
        "source": row["source_label"],
        "source_url": row["source_url"],
        "notes": row["notes"],
        "timestamp": row["updated_at"],
        "status": "manual",
    } for row in rows]


def save_retailer_quote(
    retailer_id: str, city: str, gold_22k_per_g: float | None, gold_24k_per_g: float | None,
    coin_10g_total: float | None, making_charge_pct: float | None, source_label: str,
    source_url: str | None = None, notes: str | None = None,
) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO retailer_quotes(
                retailer_id, city, gold_22k_per_g, gold_24k_per_g, coin_10g_total,
                making_charge_pct, source_label, source_url, notes, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(retailer_id, city) DO UPDATE SET
                gold_22k_per_g=excluded.gold_22k_per_g,
                gold_24k_per_g=excluded.gold_24k_per_g,
                coin_10g_total=excluded.coin_10g_total,
                making_charge_pct=excluded.making_charge_pct,
                source_label=excluded.source_label, source_url=excluded.source_url,
                notes=excluded.notes, updated_at=excluded.updated_at""",
            (retailer_id, city, gold_22k_per_g, gold_24k_per_g, coin_10g_total,
             making_charge_pct, source_label, source_url, notes, timestamp),
        )
    return {
        "retailer_id": retailer_id, "city": city, "gold_22k_per_g": gold_22k_per_g,
        "gold_24k_per_g": gold_24k_per_g, "coin_10g_total": coin_10g_total,
        "making_charge_pct": making_charge_pct, "source": source_label,
        "source_url": source_url, "notes": notes, "timestamp": timestamp, "status": "manual",
    }


def delete_retailer_quote(retailer_id: str, city: str = "Pune") -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM retailer_quotes WHERE retailer_id=? AND lower(city)=lower(?)",
            (retailer_id, city),
        )
    return cur.rowcount > 0
