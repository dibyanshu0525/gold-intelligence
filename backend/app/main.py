from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import db
from .config import ENV
from .service import dashboard_payload, refresh_and_store
from .retailers import RETAILER_BY_ID, retailer_directory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gold-intelligence")

poll_task: asyncio.Task | None = None


async def _poll_loop() -> None:
    while True:
        try:
            await refresh_and_store()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduled market refresh failed")
        # XAUS' documented cache interval is 60 seconds; respect that minimum even
        # when a user configures a shorter backend poll. Provider adapters have
        # their own longer TTLs for quota-limited sources.
        await asyncio.sleep(max(60, ENV.poll_seconds))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global poll_task
    db.init_db()
    poll_task = asyncio.create_task(_poll_loop())
    yield
    if poll_task:
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Gold Intelligence API",
    version="1.2.1",
    description="Live gold price parity, Indian benchmarks, retail quote comparison and purchase analysis.",
    lifespan=lifespan,
)

origins = [item.strip() for item in ENV.cors_origins.split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


class SettingsUpdate(BaseModel):
    import_duty_pct: float | None = Field(default=None, ge=0, le=100)
    domestic_premium_pct: float | None = Field(default=None, ge=-20, le=50)
    local_cost_inr_per_10g: float | None = Field(default=None, ge=-100000, le=100000)
    gst_pct: float | None = Field(default=None, ge=0, le=30)
    coin_premium_pct: float | None = Field(default=None, ge=0, le=50)
    coin_fixed_fee_inr: float | None = Field(default=None, ge=0, le=100000)
    coin_weight_g: float | None = Field(default= None, gt=0, le=1000)
    kalyan_max_premium_pct: float | None = Field(default=None, ge=0, le=20)
    watch_discount_pct: float | None = Field(default=None, ge=0, le=20)
    alert_move_pct: float | None = Field(default=None, gt=0, le=50)


class ManualOverride(BaseModel):
    field: str
    value: float = Field(gt=0)
    source_label: str = Field(default="Pune showroom quote", min_length=2, max_length=100)


class RetailerQuote(BaseModel):
    retailer_id: str
    city: str = Field(default="Pune", min_length=2, max_length=80)
    gold_22k_per_g: float | None = Field(default=None, gt=0, le=1000000)
    gold_24k_per_g: float | None = Field(default=None, gt=0, le=1000000)
    coin_10g_total: float | None = Field(default=None, gt=0, le=10000000)
    making_charge_pct: float | None = Field(default=None, ge=0, le=100)
    source_label: str = Field(default="Verified retailer page / showroom quote", min_length=2, max_length=120)
    source_url: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=500)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "Gold Intelligence API", "docs": "/docs", "health": "/api/health"}


@app.get("/api/health")
async def health() -> dict[str, Any]:
    snapshot = dashboard_payload() or {}
    return {
        "status": "ok",
        "poll_seconds": max(60, ENV.poll_seconds),
        "providers": {
            "xaus": ENV.xaus_enabled,
            "gold_api_com": ENV.gold_api_com_enabled,
            "goldapi_dev": bool(ENV.goldapi_dev_key),
            "goldprice_dev": ENV.goldprice_enabled,
            "frankfurter_fx": ENV.frankfurter_enabled,
            "twelve_data_fx": bool(ENV.twelve_data_api_key),
            "metals_dev": bool(ENV.metals_dev_api_key),
            "ibja_public_page_fallback": True,
            "kalyan_public_page_fallback": True,
        },
        "provider_health": snapshot.get("provider_health", {}),
        "selected_provider": snapshot.get("selected_provider", {}),
    }


@app.get("/api/providers")
async def get_provider_status() -> dict[str, Any]:
    snapshot = dashboard_payload() or {}
    return {
        "selected_provider": snapshot.get("selected_provider", {}),
        "provider_health": snapshot.get("provider_health", {}),
        "source_errors": snapshot.get("source_errors", {}),
        "captured_at": snapshot.get("captured_at"),
    }


@app.get("/api/dashboard")
async def dashboard() -> dict[str, Any]:
    current = dashboard_payload()
    if current is None:
        current = await refresh_and_store()
    return current


@app.post("/api/refresh")
async def refresh() -> dict[str, Any]:
    try:
        return await refresh_and_store()
    except Exception as exc:
        logger.exception("Manual refresh failed")
        raise HTTPException(status_code=502, detail=f"Refresh failed: {str(exc)[:250]}") from exc


@app.get("/api/history")
async def get_history(hours: int = 24) -> dict[str, Any]:
    hours = max(1, min(hours, 24 * 45))
    return {"hours": hours, "items": db.history(hours)}


@app.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    return {"settings": db.get_settings(), "overrides": db.get_overrides()}


@app.post("/api/settings")
async def save_settings(payload: SettingsUpdate) -> dict[str, Any]:
    values = {key: value for key, value in payload.model_dump(exclude_none=True).items()}
    return {"settings": db.update_settings(values)}


@app.post("/api/overrides")
async def create_override(payload: ManualOverride) -> dict[str, Any]:
    allowed = {
        "xau_usd_oz", "usd_inr", "ibja_999_10g", "mcx_999_10g",
        "kalyan_24k_10g", "kalyan_22k_10g",
    }
    if payload.field not in allowed:
        raise HTTPException(status_code=400, detail=f"field must be one of: {', '.join(sorted(allowed))}")
    value = db.set_override(payload.field, payload.value, payload.source_label)
    return {"field": payload.field, "override": value}


@app.delete("/api/overrides/{field}")
async def remove_override(field: str) -> dict[str, Any]:
    allowed = {
        "xau_usd_oz", "usd_inr", "ibja_999_10g", "mcx_999_10g",
        "kalyan_24k_10g", "kalyan_22k_10g",
    }
    if field not in allowed:
        raise HTTPException(status_code=400, detail="Unknown override field")
    return {"deleted": db.delete_override(field), "field": field}


@app.get("/api/retailers")
async def get_retailers(city: str = "Pune") -> dict[str, Any]:
    city = city.strip() or "Pune"
    latest = dashboard_payload() or {}
    source_data = latest.get("sources") or {}
    return retailer_directory(city, db.get_retailer_quotes(city), source_data)


@app.post("/api/retailer-quotes")
async def create_retailer_quote(payload: RetailerQuote) -> dict[str, Any]:
    if payload.retailer_id not in RETAILER_BY_ID:
        raise HTTPException(status_code=400, detail="Unknown retailer_id. Refresh the retailer directory.")
    if all(value is None for value in (payload.gold_22k_per_g, payload.gold_24k_per_g, payload.coin_10g_total)):
        raise HTTPException(status_code=400, detail="Enter at least one 22K rate, 24K rate or 10g coin final price.")
    quote = db.save_retailer_quote(**payload.model_dump())
    return {"saved": True, "quote": quote}


@app.delete("/api/retailer-quotes/{retailer_id}")
async def remove_retailer_quote(retailer_id: str, city: str = "Pune") -> dict[str, Any]:
    if retailer_id not in RETAILER_BY_ID:
        raise HTTPException(status_code=400, detail="Unknown retailer_id")
    return {"deleted": db.delete_retailer_quote(retailer_id, city), "retailer_id": retailer_id, "city": city}
