from __future__ import annotations

import asyncio
import copy
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import httpx

from .config import ENV
from .pricing import TROY_OUNCE_GRAMS
from .providers import MetalsDevProvider, point, scrape_ibja, scrape_kalyan

USER_AGENT = "GoldIntelligence/1.2 (+personal market-monitor)"

# Process-local cache: it protects free quotas during scheduled polls and manual refreshes.
_CACHE: dict[str, dict[str, Any]] = {}
_LOCKS: dict[str, asyncio.Lock] = {}
_HEALTH: dict[str, dict[str, Any]] = {}
_RETRY_AT: dict[str, float] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_timestamp(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            return None
    return None


def _num(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def parse_xaus(body: dict[str, Any]) -> dict[str, Any]:
    """Normalize XAUS /api/v1/spot?currency=INR&unit=troy_oz."""
    spot_usd = _num(body.get("spot_usd_oz"))
    fx = _num(body.get("fx_rate"))
    xau = body.get("xau") or {}
    inr_oz = _num(xau.get("price")) if str(xau.get("currency", "INR")).upper() == "INR" else None
    state = body.get("data_state") or {}
    spot_ts = _parse_timestamp(body.get("price_as_of") or state.get("as_of") or body.get("updated_at"))
    fx_ts = _parse_timestamp(body.get("updated_at") or state.get("as_of"))
    stale = bool(body.get("stale")) or state.get("status") == "stale"
    spot_status = "stale" if stale or state.get("status") == "unavailable" else "live"
    fx_stale = bool(body.get("fx_stale"))
    fx_status = "delayed" if fx_stale else ("stale" if stale else "live")
    return {
        "xau_usd": point(spot_usd, "USD / troy oz", "XAUS live spot API", spot_status, spot_ts,
                          "Indicative spot, refreshed/cached by XAUS; not an executable dealer quote."),
        "usd_inr": point(fx, "INR per USD", "XAUS FX conversion", fx_status, fx_ts,
                         "USD/INR conversion returned with XAUS spot. Check fx_stale before relying on it."),
        "xau_inr_10g": point(inr_oz * 10.0 / TROY_OUNCE_GRAMS if inr_oz is not None else None,
                              "INR / 10g", "XAUS XAU/INR converted spot", spot_status, spot_ts,
                              "Raw international spot-equivalent converted to INR; excludes Indian duties, GST and retail premiums."),
        "data_state": state,
        "fx_stale": fx_stale,
    }



def parse_gold_api_com(usd_body: dict[str, Any], inr_body: dict[str, Any]) -> dict[str, Any]:
    """Normalize keyless Gold-API.com /price/XAU and /price/XAU/INR responses."""
    usd_price = _num(usd_body.get("price"))
    inr_price = _num(inr_body.get("price"))
    usd_ts = _parse_timestamp(usd_body.get("updatedAt"))
    inr_ts = _parse_timestamp(inr_body.get("updatedAt"))
    return {
        "xau_usd": point(usd_price, "USD / troy oz", "Gold-API.com live spot", "live" if usd_price is not None else "unavailable", usd_ts,
                          "Keyless live spot endpoint; provider says prices refresh every 30 seconds. Indicative, not an executable quote."),
        "xau_inr_10g": point(inr_price * 10.0 / TROY_OUNCE_GRAMS if inr_price is not None else None, "INR / 10g",
                              "Gold-API.com XAU/INR converted spot", "live" if inr_price is not None else "unavailable", inr_ts,
                              "Raw XAU spot converted to INR by Gold-API.com; excludes Indian duties, GST and retail premiums."),
    }

def parse_goldapi_dev(spot_body: dict[str, Any], rates_body: dict[str, Any]) -> dict[str, Any]:
    """Normalize GoldAPI.dev /price/XAU/USD and /rates responses."""
    spot_value = _num(spot_body.get("price"))
    fx_rates = rates_body.get("rates") or {}
    fx_value = _num(fx_rates.get("INR") or fx_rates.get("inr"))
    spot_ts = _parse_timestamp(spot_body.get("updatedAt"))
    fx_ts = _parse_timestamp(rates_body.get("_server_time"))
    return {
        "xau_usd": point(spot_value, "USD / troy oz", "GoldAPI.dev", "live" if spot_value is not None else "unavailable", spot_ts,
                          "GoldAPI.dev free tier: live spot; 100 requests/hour; attribution link required for commercial display."),
        "usd_inr": point(fx_value, "INR per USD", "GoldAPI.dev FX rates", "live" if fx_value is not None else "unavailable", fx_ts,
                         "USD base FX rates from GoldAPI.dev."),
        "quota": {
            "remaining": None,
            "reset": None,
        },
    }


def parse_goldapi_dev_inr(body: dict[str, Any]) -> dict[str, Any]:
    gram = _num(body.get("gram"))
    timestamp = _parse_timestamp(body.get("updatedAt"))
    return {
        "xau_inr_10g": point(gram * 10.0 if gram is not None else None, "INR / 10g",
                              "GoldAPI.dev XAU/INR quote", "live" if gram is not None else "unavailable", timestamp,
                              "24K raw spot-equivalent; source currency conversion is internal to GoldAPI.dev."),
    }


def parse_goldprice_dev(body: dict[str, Any]) -> dict[str, Any]:
    price = _num(body.get("price"))
    timestamp = _parse_timestamp(body.get("computed_at") or body.get("timestamp"))
    stale = bool(body.get("is_stale"))
    return {
        "xau_inr_10g": point(price * 10.0 / TROY_OUNCE_GRAMS if price is not None else None,
                              "INR / 10g", "GoldPrice.dev XAU-INR-SPOT", "stale" if stale else "delayed", timestamp,
                              "Free tier is delayed by 15 minutes. Raw spot-equivalent; not a physical dealer quote."),
    }


def parse_frankfurter(body: dict[str, Any]) -> dict[str, Any]:
    # Frankfurter v2 single-pair response: {date, base, quote, rate}.
    # v1 {date, base, rates: {INR}} remains accepted for compatibility.
    rate = _num(body.get("rate")) if str(body.get("quote", "")).upper() == "INR" else None
    if rate is None:
        rate = _num((body.get("rates") or {}).get("INR"))
    date = body.get("date")
    timestamp = _parse_timestamp(f"{date}T00:00:00Z") if date else None
    return {
        "usd_inr": point(rate, "INR per USD", "Frankfurter daily reference FX", "delayed" if rate is not None else "unavailable", timestamp,
                         "Daily reference rate; not an intraday executable USD/INR quote."),
    }


def _mark_stale(data: dict[str, Any], note: str) -> dict[str, Any]:
    result = copy.deepcopy(data)
    for value in result.values():
        if isinstance(value, dict) and "value" in value:
            value["status"] = "stale"
            old = value.get("note") or ""
            value["note"] = f"{old} Last known cached value after provider error: {note}".strip()
    return result


async def _cached_fetch(
    name: str,
    ttl_seconds: int,
    enabled: bool,
    loader: Callable[[], Awaitable[dict[str, Any]]],
    request_weight: int = 1,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    health = _HEALTH.setdefault(name, {
        "name": name,
        "enabled": enabled,
        "status": "not_polled",
        "request_count": 0,
        "cache_hits": 0,
        "last_attempt_at": None,
        "last_success_at": None,
        "last_error": None,
        "cache_ttl_seconds": ttl_seconds,
        "cache_age_seconds": None,
        "rate_limit_remaining": None,
        "rate_limit_reset": None,
    })
    health["enabled"] = enabled
    health["cache_ttl_seconds"] = ttl_seconds
    if not enabled:
        health["status"] = "disabled"
        return None, copy.deepcopy(health)

    now_mono = time.monotonic()
    cached = _CACHE.get(name)
    retry_at = _RETRY_AT.get(name, 0.0)
    if now_mono < retry_at:
        if cached:
            health["status"] = "stale"
            health["cache_age_seconds"] = round(now_mono - cached["stored_mono"], 1)
            return _mark_stale(cached["data"], health.get("last_error") or "provider retry backoff"), copy.deepcopy(health)
        health["status"] = "error"
        return None, copy.deepcopy(health)
    if cached and now_mono - cached["stored_mono"] < ttl_seconds:
        health["status"] = "cached"
        health["cache_age_seconds"] = round(now_mono - cached["stored_mono"], 1)
        health["cache_hits"] += 1
        return copy.deepcopy(cached["data"]), copy.deepcopy(health)

    lock = _LOCKS.setdefault(name, asyncio.Lock())
    async with lock:
        now_mono = time.monotonic()
        cached = _CACHE.get(name)
        retry_at = _RETRY_AT.get(name, 0.0)
        if now_mono < retry_at:
            if cached:
                health["status"] = "stale"
                health["cache_age_seconds"] = round(now_mono - cached["stored_mono"], 1)
                return _mark_stale(cached["data"], health.get("last_error") or "provider retry backoff"), copy.deepcopy(health)
            health["status"] = "error"
            return None, copy.deepcopy(health)
        if cached and now_mono - cached["stored_mono"] < ttl_seconds:
            health["status"] = "cached"
            health["cache_age_seconds"] = round(now_mono - cached["stored_mono"], 1)
            health["cache_hits"] += 1
            return copy.deepcopy(cached["data"]), copy.deepcopy(health)
        health["last_attempt_at"] = _now()
        health["request_count"] += request_weight
        try:
            data = await loader()
            quota = data.get("quota") if isinstance(data, dict) else None
            if isinstance(quota, dict):
                health["rate_limit_remaining"] = quota.get("remaining")
                health["rate_limit_reset"] = quota.get("reset")
            _CACHE[name] = {"data": copy.deepcopy(data), "stored_mono": time.monotonic()}
            _RETRY_AT.pop(name, None)
            health["status"] = "ok"
            health["last_success_at"] = _now()
            health["last_error"] = None
            health["cache_age_seconds"] = 0
            return copy.deepcopy(data), copy.deepcopy(health)
        except Exception as exc:
            health["last_error"] = f"{type(exc).__name__}: {str(exc)[:220]}"
            # Back off for at least the source TTL after a failure. This matters
            # most for free monthly-quota endpoints such as GoldPrice.dev.
            _RETRY_AT[name] = time.monotonic() + max(60, ttl_seconds)
            if cached:
                age = max(0.0, time.monotonic() - cached["stored_mono"])
                health["status"] = "stale"
                health["cache_age_seconds"] = round(age, 1)
                return _mark_stale(cached["data"], health["last_error"]), copy.deepcopy(health)
            health["status"] = "error"
            health["cache_age_seconds"] = None
            return None, copy.deepcopy(health)


async def _get_json(client: httpx.AsyncClient, url: str, *, headers: dict[str, str] | None = None,
                    params: dict[str, Any] | None = None) -> tuple[dict[str, Any], httpx.Headers]:
    response = await client.get(url, headers=headers, params=params)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("Provider returned a non-object JSON response")
    if body.get("error"):
        raise RuntimeError(str(body.get("error"))[:180])
    return body, response.headers


async def collect_multi_source_market_data(client: httpx.AsyncClient) -> dict[str, Any]:
    """Fetch market feeds with per-provider caches, quota-aware polling and failover."""
    timeout_headers = {"User-Agent": USER_AGENT}

    async def load_xaus() -> dict[str, Any]:
        body, _ = await _get_json(client, "https://xaus.com/api/v1/spot", headers=timeout_headers,
                                  params={"currency": "INR", "unit": "troy_oz", "compact": "1"})
        return parse_xaus(body)

    async def load_gold_api_com() -> dict[str, Any]:
        async def fetch(currency: str):
            return await _get_json(client, f"https://api.gold-api.com/price/XAU/{currency}", headers=timeout_headers)
        (usd_body, _), (inr_body, _) = await asyncio.gather(fetch("USD"), fetch("INR"))
        return parse_gold_api_com(usd_body, inr_body)

    async def load_goldapi_dev() -> dict[str, Any]:
        headers = {**timeout_headers, "X-API-Key": ENV.goldapi_dev_key}
        async def fetch(path: str):
            return await _get_json(client, f"https://goldapi.dev/api/v1/{path}", headers=headers)
        (spot, spot_headers), (rates, rate_headers) = await asyncio.gather(fetch("price/XAU/USD"), fetch("rates"))
        parsed = parse_goldapi_dev(spot, rates)
        remaining = rate_headers.get("X-RateLimit-Remaining") or spot_headers.get("X-RateLimit-Remaining")
        reset = rate_headers.get("X-RateLimit-Reset") or spot_headers.get("X-RateLimit-Reset")
        parsed["quota"] = {"remaining": int(remaining) if remaining and remaining.isdigit() else None, "reset": reset}
        # A separate INR quote gives an independent check of the complete XAU/INR path.
        try:
            (inr_body, _) = await _get_json(client, "https://goldapi.dev/api/v1/price/XAU/INR/24", headers=headers)
            parsed.update(parse_goldapi_dev_inr(inr_body))
        except Exception as exc:
            parsed["xau_inr_10g"] = point(None, "INR / 10g", "GoldAPI.dev XAU/INR quote", "unavailable", note=f"Optional INR cross-check failed: {str(exc)[:160]}")
        return parsed

    async def load_goldprice_dev() -> dict[str, Any]:
        goldprice_headers = dict(timeout_headers)
        if ENV.goldprice_api_key:
            goldprice_headers["Authorization"] = f"Bearer {ENV.goldprice_api_key}"
        body, _ = await _get_json(client, "https://api.goldprice.dev/v1/spot/XAU",
                                  headers=goldprice_headers, params={"currency": "INR", "include": "sources"})
        parsed = parse_goldprice_dev(body)
        parsed["source_metadata"] = {"is_stale": bool(body.get("is_stale")), "computed_at": body.get("computed_at")}
        return parsed

    async def load_frankfurter() -> dict[str, Any]:
        body, _ = await _get_json(client, "https://api.frankfurter.dev/v2/rate/usd/inr",
                                  headers=timeout_headers)
        return parse_frankfurter(body)

    async def load_twelve_data() -> dict[str, Any]:
        body, _ = await _get_json(client, "https://api.twelvedata.com/price",
                                  headers=timeout_headers, params={"symbol": "USD/INR", "apikey": ENV.twelve_data_api_key})
        value = _num(body.get("price"))
        # /price does not return an exchange timestamp. Retrieval time is explicitly disclosed.
        return {"usd_inr": point(value, "INR per USD", "Twelve Data USD/INR", "delayed" if value is not None else "unavailable", _now(),
                                  "The /price response has no quote timestamp; timestamp is retrieval time. Use as a cross-check only.")}

    async def load_metals_dev() -> dict[str, Any]:
        provider = MetalsDevProvider(client)
        spot, fx = await asyncio.gather(provider.spot(), provider.fx())
        return {**spot, **fx}

    tasks = {
        "xaus": _cached_fetch("xaus", 60, ENV.xaus_enabled, load_xaus),
        "gold_api_com": _cached_fetch("gold_api_com", 30, ENV.gold_api_com_enabled, load_gold_api_com, request_weight=2),
        "goldapi_dev": _cached_fetch("goldapi_dev", 300, bool(ENV.goldapi_dev_key), load_goldapi_dev, request_weight=3),
        "goldprice_dev": _cached_fetch("goldprice_dev", 1200, ENV.goldprice_enabled, load_goldprice_dev),
        "frankfurter_fx": _cached_fetch("frankfurter_fx", 3600, ENV.frankfurter_enabled, load_frankfurter),
        "twelve_data_fx": _cached_fetch("twelve_data_fx", 300, bool(ENV.twelve_data_api_key), load_twelve_data),
        "metals_dev": _cached_fetch("metals_dev", 600, bool(ENV.metals_dev_api_key), load_metals_dev, request_weight=2),
    }
    results = await asyncio.gather(*tasks.values())
    raw = {name: result[0] for name, result in zip(tasks, results)}
    health = {name: result[1] for name, result in zip(tasks, results)}

    # Deterministic provider order: XAUS first (one keyless call covers XAU and FX),
    # then optional live feeds, with the 15-minute delayed feed last.
    xau_candidates = [
        ("xaus", (raw.get("xaus") or {}).get("xau_usd")),
        ("gold_api_com", (raw.get("gold_api_com") or {}).get("xau_usd")),
        ("goldapi_dev", (raw.get("goldapi_dev") or {}).get("xau_usd")),
        ("metals_dev", (raw.get("metals_dev") or {}).get("xau_usd_oz")),
    ]
    fx_candidates = [
        ("xaus", (raw.get("xaus") or {}).get("usd_inr")),
        ("goldapi_dev", (raw.get("goldapi_dev") or {}).get("usd_inr")),
        ("metals_dev", (raw.get("metals_dev") or {}).get("usd_inr")),
        ("twelve_data_fx", (raw.get("twelve_data_fx") or {}).get("usd_inr")),
        ("frankfurter_fx", (raw.get("frankfurter_fx") or {}).get("usd_inr")),
    ]

    def choose(candidates: list[tuple[str, dict[str, Any] | None]]) -> tuple[dict[str, Any] | None, str | None]:
        for allowed in ({"live", "manual"}, {"delayed"}, {"stale"}):
            for provider_name, candidate in candidates:
                if candidate and candidate.get("value") is not None and candidate.get("status") in allowed:
                    return candidate, provider_name
        return None, None

    xau, xau_provider = choose(xau_candidates)
    fx, fx_provider = choose(fx_candidates)
    checks: dict[str, Any] = {}
    for name, key in (("xaus", "xaus"), ("gold_api_com", "gold_api_com"), ("goldapi_dev", "goldapi_dev"), ("goldprice_dev", "goldprice_dev")):
        data = raw.get(key) or {}
        item = data.get("xau_inr_10g")
        if item and item.get("value") is not None:
            checks[name] = item
    return {
        "selected": {"xau_usd": xau, "usd_inr": fx},
        "selected_provider": {"xau_usd": xau_provider, "usd_inr": fx_provider},
        "cross_checks": checks,
        "provider_health": health,
        "provider_errors": {name: item.get("last_error") for name, item in health.items() if item.get("last_error")},
    }


async def collect_india_reference_data(client: httpx.AsyncClient) -> dict[str, Any]:
    """Fetch IBJA, MCX authority and Kalyan public page without over-polling them."""
    timeout_headers = {"User-Agent": USER_AGENT}

    async def load_ibja_page():
        return await scrape_ibja(client)

    async def load_kalyan_page():
        return await scrape_kalyan(client)

    ibja_tasks: list[Awaitable[dict[str, Any]]] = [
        _cached_fetch("ibja_public", 900, True, load_ibja_page),
        _cached_fetch("kalyan_public", 900, True, load_kalyan_page),
    ]
    names = ["ibja_public", "kalyan_public"]

    async def load_authority(authority: str):
        return await MetalsDevProvider(client).authority(authority)

    if ENV.metals_dev_api_key:
        ibja_tasks.extend([
            _cached_fetch("metals_dev_ibja", 1800, True, lambda: load_authority("ibja")),
            _cached_fetch("metals_dev_mcx", 1800, True, lambda: load_authority("mcx")),
        ])
        names.extend(["metals_dev_ibja", "metals_dev_mcx"])
    results = await asyncio.gather(*ibja_tasks)
    raw = {name: item[0] for name, item in zip(names, results)}
    health = {name: item[1] for name, item in zip(names, results)}

    def usable(preferred: str, fallback: str, field: str) -> dict[str, Any] | None:
        primary = (raw.get(preferred) or {}).get(field)
        secondary = (raw.get(fallback) or {}).get(field)
        for candidate in (primary, secondary):
            if isinstance(candidate, dict) and candidate.get("value") is not None:
                return candidate
        return None

    ibja_primary = "metals_dev_ibja" if ENV.metals_dev_api_key else "ibja_public"
    mcx = (raw.get("metals_dev_mcx") or {}).get("mcx_999_10g")
    kalyan = raw.get("kalyan_public") or {}
    return {
        "sources": {
            "ibja_999_10g": usable(ibja_primary, "ibja_public", "ibja_999_10g"),
            "mcx_999_10g": mcx,
            "kalyan_24k_10g": kalyan.get("kalyan_24k_10g"),
            "kalyan_22k_10g": kalyan.get("kalyan_22k_10g"),
        },
        "provider_health": health,
    }


def clear_provider_cache() -> None:
    """Test helper; safe to call on startup or in unit tests."""
    _CACHE.clear()
    _HEALTH.clear()
    _LOCKS.clear()
    _RETRY_AT.clear()
