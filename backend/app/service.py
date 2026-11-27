from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from . import db
from .config import ENV
from .pricing import (
    build_recommendation,
    coin_invoice_estimate,
    compare_pct,
    global_spot_inr_per_gram,
    landed_reference_999_10g,
    percent_change,
    utc_now,
)
from .providers import point
from .market_data import collect_india_reference_data, collect_multi_source_market_data


def _value(source: dict[str, Any] | None, key: str) -> float | None:
    if not source:
        return None
    item = source.get(key)
    if isinstance(item, dict):
        try:
            return float(item.get("value")) if item.get("value") is not None else None
        except (TypeError, ValueError):
            return None
    try:
        return float(item) if item is not None else None
    except (TypeError, ValueError):
        return None


def _manual_point(override: dict[str, Any], key: str, unit: str) -> dict[str, Any]:
    return point(override["value"], unit, f"Manual override — {override['source']}", "manual", override["timestamp"], "Entered by the dashboard user; verify the quote independently.")


async def _safe(coro, fallback: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return await coro, None
    except Exception as exc:  # source failures are shown to the user; the whole dashboard remains available
        return fallback, f"{type(exc).__name__}: {str(exc)[:220]}"


def _age_seconds(point_data: dict[str, Any] | None) -> float | None:
    if not point_data or not point_data.get("timestamp"):
        return None
    try:
        dt = datetime.fromisoformat(point_data["timestamp"].replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())
    except (ValueError, TypeError):
        return None


def _market_state() -> dict[str, Any]:
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    from datetime import timedelta
    # MCX non-agri closing time follows US daylight-saving time: 23:30 while
    # New York is on DST and 23:55 after the US switches back to standard time.
    new_york_now = datetime.now(ZoneInfo("America/New_York"))
    us_dst = bool(new_york_now.dst() and new_york_now.dst() != timedelta(0))
    close_minute = 30 if us_dst else 55
    within_session = (now.hour > 9 or (now.hour == 9 and now.minute >= 0)) and (now.hour < 23 or (now.hour == 23 and now.minute <= close_minute))
    open_now = now.weekday() < 5 and within_session
    close_text = f"23:{close_minute:02d}"
    return {
        "india_time": now.isoformat(),
        "mcx_session": "OPEN (time-based estimate)" if open_now else "CLOSED (time-based estimate)",
        "mcx_open": open_now,
        "mcx_note": f"Weekdays 09:00–{close_text} IST using the current US daylight-saving season; exchange holidays are not integrated.",
        "ibja_note": "IBJA/IGM benchmark sessions are published on a schedule (commonly 11:00 and 17:00 IST); session/holiday availability should be confirmed on the source page.",
    }


def _build_signals(snapshot: dict[str, Any], settings: dict[str, float], older: list[dict[str, Any]]) -> dict[str, Any]:
    sources = snapshot["sources"]
    calculations = snapshot["calculations"]
    xau = sources.get("xau_usd")
    fx = sources.get("usd_inr")
    ibja = sources.get("ibja_999_10g")
    kalyan = sources.get("kalyan_24k_10g")
    market_points = [xau, fx]
    reference_points = [ibja, kalyan]
    required_present = all(p and p.get("value") is not None for p in (xau, fx, ibja, kalyan))
    market_fresh = all(p and p.get("status") in {"live", "manual"} and (_age_seconds(p) or 0) <= 600 for p in market_points)
    reference_fresh = all(p and p.get("status") not in {"stale", "unavailable"} and (_age_seconds(p) or 0) <= 36 * 3600 for p in reference_points)
    data_fresh = required_present and market_fresh and reference_fresh

    rec = build_recommendation(
        data_fresh=data_fresh,
        ibja_999_10g=calculations.get("ibja_999_10g"),
        kalyan_24k_10g=calculations.get("kalyan_24k_10g"),
        kalyan_premium_pct=calculations.get("kalyan_vs_ibja_pct"),
        model_gap_pct=calculations.get("ibja_vs_model_pct"),
        max_kalyan_premium_pct=settings["kalyan_max_premium_pct"],
        watch_discount_pct=settings["watch_discount_pct"],
    )

    alerts: list[dict[str, Any]] = []
    if not sources.get("xau_usd", {}).get("value"):
        alerts.append({"level": "warning", "title": "Global gold feed unavailable", "detail": "XAUS is the default keyless source. Configure GoldAPI.dev or retain Metals.Dev as optional fallbacks if the primary feed is unavailable."})
    if not sources.get("usd_inr", {}).get("value"):
        alerts.append({"level": "warning", "title": "USD/INR feed unavailable", "detail": "XAUS supplies the primary conversion; GoldAPI.dev, Twelve Data and Frankfurter are optional cross-check/fallback sources."})
    if not sources.get("ibja_999_10g", {}).get("value"):
        alerts.append({"level": "warning", "title": "IBJA benchmark missing", "detail": "Check IBJA page access or enter the current 999 AM/PM value manually."})
    if not sources.get("kalyan_24k_10g", {}).get("value"):
        alerts.append({"level": "warning", "title": "Kalyan quote missing", "detail": "Enter a showroom quote; the published page may not expose Pune rates."})

    cross_spread = calculations.get("xau_inr_cross_source_spread_pct")
    if cross_spread is not None and cross_spread > 0.75:
        alerts.append({"level": "warning", "title": "Global provider prices disagree", "detail": f"The available XAU/INR spot cross-checks differ by {cross_spread:.2f}%. Review provider timestamps, currencies and source status before acting on any retail spread."})

    premium = calculations.get("kalyan_vs_ibja_pct")
    if premium is not None and premium > settings["kalyan_max_premium_pct"]:
        alerts.append({"level": "warning", "title": "Kalyan premium above your tolerance", "detail": f"Published Kalyan 24K is {premium:.2f}% above IBJA 999. Ask for the final 10g coin quotation and compare another dealer."})
    elif premium is not None and premium <= 0:
        alerts.append({"level": "good", "title": "Kalyan quote is at/below IBJA", "detail": "This is a favourable published-rate comparison, subject to billing-time price, coin premium and buyback terms."})

    move = None
    previous = older[-1] if older else None
    if previous:
        prev_price = (previous.get("calculations") or {}).get("xau_inr_raw_10g")
        cur_price = calculations.get("xau_inr_raw_10g")
        move = percent_change(cur_price, prev_price)
    calculations["last_poll_move_pct"] = move

    # 1h / 24h change is shown only when the locally collected history has a
    # sufficiently old observation. No extrapolation or fabricated daily data.
    now_dt = datetime.now(timezone.utc)
    def find_reference(hours: int) -> dict[str, Any] | None:
        target = now_dt.timestamp() - hours * 3600
        candidates = []
        for item in older:
            try:
                stamp = datetime.fromisoformat(item.get("captured_at", "").replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                if stamp.timestamp() <= target:
                    candidates.append(item)
            except (TypeError, ValueError):
                continue
        return candidates[-1] if candidates else None

    def historical_pct(path: str, current_value: float | None, hours: int) -> float | None:
        reference = find_reference(hours)
        if not reference or current_value is None:
            return None
        old_value = (reference.get("calculations") or {}).get(path)
        return percent_change(current_value, old_value)

    fx_current = _value(sources, "usd_inr")
    ibja_current = calculations.get("ibja_999_10g")
    calculations["xau_inr_1h_change_pct"] = historical_pct("xau_inr_raw_10g", calculations.get("xau_inr_raw_10g"), 1)
    calculations["xau_inr_24h_change_pct"] = historical_pct("xau_inr_raw_10g", calculations.get("xau_inr_raw_10g"), 24)
    calculations["usd_inr_24h_change_pct"] = historical_pct("usd_inr_value", fx_current, 24)
    calculations["ibja_24h_change_pct"] = historical_pct("ibja_999_10g", ibja_current, 24)
    calculations["usd_inr_value"] = fx_current
    if move is not None and abs(move) >= settings["alert_move_pct"]:
        direction = "up" if move > 0 else "down"
        alerts.append({"level": "warning" if move > 0 else "good", "title": f"Large spot-equivalent move {direction}", "detail": f"Modelled global INR equivalent moved {move:+.2f}% since the previous stored poll."})

    if calculations.get("ibja_vs_model_pct") is not None and abs(calculations["ibja_vs_model_pct"]) > 3:
        alerts.append({"level": "warning", "title": "Model spread needs review", "detail": "IBJA and the configurable import-parity estimate differ by more than 3%. Review duty, import tariff valuation, local premium and source timestamps. This is not a risk-free arbitrage signal."})

    return {"recommendation": rec, "alerts": alerts}


async def collect_snapshot() -> dict[str, Any]:
    timeout = httpx.Timeout(ENV.request_timeout)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={"User-Agent": "GoldIntelligence/1.2"}) as client:
        market_data, india_data = await asyncio.gather(
            collect_multi_source_market_data(client),
            collect_india_reference_data(client),
        )

    selected = market_data.get("selected") or {}
    india_sources = india_data.get("sources") or {}
    checks = market_data.get("cross_checks") or {}
    sources: dict[str, Any] = {
        "xau_usd": selected.get("xau_usd") or point(None, "USD / troy oz", "No active spot provider", "unavailable", note="Enable XAUS or Gold-API.com, or configure GoldAPI.dev / Metals.Dev as a fallback."),
        "usd_inr": selected.get("usd_inr") or point(None, "INR per USD", "No active FX provider", "unavailable", note="Enable XAUS or configure a free/optional FX fallback."),
        "ibja_999_10g": india_sources.get("ibja_999_10g") or point(None, "INR / 10g", "Not connected", "unavailable", note="Check IBJA public page or enter a verified benchmark manually."),
        "mcx_999_10g": india_sources.get("mcx_999_10g") or point(None, "INR / 10g", "Not connected", "unavailable", note="A licensed MCX or eligible authority feed is required; do not treat a proxy as live MCX data."),
        "kalyan_24k_10g": india_sources.get("kalyan_24k_10g") or point(None, "INR / 10g", "Not connected", "unavailable", note="Enter a verified showroom quote if the public page cannot be parsed."),
        "kalyan_22k_10g": india_sources.get("kalyan_22k_10g") or point(None, "INR / 10g", "Not connected", "unavailable", note="Enter a verified showroom quote if the public page cannot be parsed."),
    }
    for provider_name, item in checks.items():
        sources[f"xau_inr_{provider_name}_10g"] = item

    overrides = db.get_overrides()
    override_map = {
        "xau_usd_oz": ("xau_usd", "USD / troy oz"),
        "usd_inr": ("usd_inr", "INR per USD"),
        "ibja_999_10g": ("ibja_999_10g", "INR / 10g"),
        "mcx_999_10g": ("mcx_999_10g", "INR / 10g"),
        "kalyan_24k_10g": ("kalyan_24k_10g", "INR / 10g"),
        "kalyan_22k_10g": ("kalyan_22k_10g", "INR / 10g"),
    }
    for field, (target, unit) in override_map.items():
        if field in overrides:
            sources[target] = _manual_point(overrides[field], field, unit)

    settings = db.get_settings()
    xau = _value(sources, "xau_usd")
    fx = _value(sources, "usd_inr")
    ibja_10g = _value(sources, "ibja_999_10g")
    mcx_10g = _value(sources, "mcx_999_10g")
    kalyan_24_10g = _value(sources, "kalyan_24k_10g")
    kalyan_22_10g = _value(sources, "kalyan_22k_10g")

    calculations: dict[str, Any] = {}
    if xau is not None and fx is not None:
        raw_g = global_spot_inr_per_gram(xau, fx)
        raw_10g = raw_g * 10
        landed_10g = landed_reference_999_10g(
            xau,
            fx,
            settings["import_duty_pct"],
            settings["domestic_premium_pct"],
            settings["local_cost_inr_per_10g"],
        )
        calculations.update({
            "xau_inr_raw_per_g": raw_g,
            "xau_inr_raw_10g": raw_10g,
            "expected_landed_999_10g": landed_10g,
            "expected_landed_999_per_g": landed_10g / 10,
            "expected_916_10g": landed_10g * 0.916,
            "expected_750_10g": landed_10g * 0.75,
        })
    else:
        raw_10g = None
        landed_10g = None

    check_values = {
        key: _value(sources, f"xau_inr_{key}_10g")
        for key in ("xaus", "gold_api_com", "goldapi_dev", "goldprice_dev")
    }
    # Compare only near-live points with timestamps within about five minutes. A 15-minute
    # delayed GoldPrice.dev value remains visible but is not treated as a live divergence.
    live_checks = []
    for source_name in ("xaus", "gold_api_com", "goldapi_dev"):
        check_point = sources.get(f"xau_inr_{source_name}_10g")
        if check_point and check_point.get("value") is not None and check_point.get("status") == "live":
            live_checks.append(check_point)
    comparable_checks = []
    if len(live_checks) >= 2:
        ages = [_age_seconds(item) for item in live_checks]
        if all(age is not None and age <= 330 for age in ages):
            stamps = [datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")).timestamp() for item in live_checks]
            if max(stamps) - min(stamps) <= 330:
                comparable_checks = [_value({"x": item}, "x") for item in live_checks]
    valid_checks = [value for value in comparable_checks if value is not None]
    if len(valid_checks) >= 2:
        mean_check = sum(valid_checks) / len(valid_checks)
        calculations["xau_inr_cross_source_spread_pct"] = ((max(valid_checks) - min(valid_checks)) / mean_check) * 100 if mean_check else None
    else:
        calculations["xau_inr_cross_source_spread_pct"] = None
    for key, value in check_values.items():
        calculations[f"xau_inr_{key}_vs_primary_pct"] = compare_pct(value, raw_10g)

    calculations.update({
        "ibja_999_10g": ibja_10g,
        "mcx_999_10g": mcx_10g,
        "kalyan_24k_10g": kalyan_24_10g,
        "kalyan_22k_10g": kalyan_22_10g,
        "ibja_vs_model_pct": compare_pct(ibja_10g, landed_10g),
        "mcx_vs_ibja_pct": compare_pct(mcx_10g, ibja_10g),
        "kalyan_vs_ibja_pct": compare_pct(kalyan_24_10g, ibja_10g),
        "kalyan_22k_vs_ibja_916_pct": compare_pct(kalyan_22_10g, ibja_10g * 0.916 if ibja_10g else None),
        "gst_pct": settings["gst_pct"],
    })

    coin_base = kalyan_24_10g or ibja_10g or landed_10g
    calculations["coin_estimate"] = coin_invoice_estimate(
        coin_base,
        settings["coin_weight_g"],
        settings["coin_premium_pct"],
        settings["coin_fixed_fee_inr"],
        settings["gst_pct"],
    )
    calculations["coin_estimate_basis"] = "Kalyan published 24K" if kalyan_24_10g else ("IBJA 999 reference" if ibja_10g else "modelled import-parity estimate")

    history = db.history(24 * 45)
    snapshot = {
        "captured_at": utc_now(),
        "sources": sources,
        "calculations": calculations,
        "settings": settings,
        "market": _market_state(),
        "selected_provider": market_data.get("selected_provider", {}),
        "provider_health": {**(market_data.get("provider_health") or {}), **(india_data.get("provider_health") or {})},
        "source_errors": {**(market_data.get("provider_errors") or {}), **{
            name: data.get("last_error") for name, data in (india_data.get("provider_health") or {}).items() if data.get("last_error")
        }},
    }
    snapshot.update(_build_signals(snapshot, settings, history))
    return snapshot


async def refresh_and_store() -> dict[str, Any]:
    snapshot = await collect_snapshot()
    db.save_snapshot(snapshot)
    return snapshot


def dashboard_payload() -> dict[str, Any] | None:
    return db.latest_snapshot()
