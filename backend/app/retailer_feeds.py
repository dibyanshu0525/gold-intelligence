from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup


USER_AGENT = "GoldIntelligence/1.3 (+personal market-monitor)"
CACHE_TTL_SECONDS = 900
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_HEALTH: dict[str, dict[str, Any]] = {}
_LOCKS: dict[str, asyncio.Lock] = {}


def _number(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(",", "").replace("₹", "").strip())
    except (TypeError, ValueError):
        return None


def _plain_text(html: str) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser").get_text(" ", strip=True)).strip()


def _tanishq_rate(text: str, purity: int) -> float | None:
    # Tanishq labels each section as e.g. "22 Kt Gold Rate". The visible
    # section defaults to 22K; a selected 24K section is parsed when published.
    heading = re.search(rf"\b{purity}\s*Kt\s*Gold\s*Rate\b", text, re.IGNORECASE)
    if not heading:
        heading = re.search(rf"\b{purity}\s*Karat\s*Gold\s*Rate\b", text, re.IGNORECASE)
    if not heading:
        return None

    section = text[heading.end():]
    next_heading = re.search(r"\b(?:18|22|24)\s*(?:Kt|Karat)\s*Gold\s*Rate\b|Gold\s*Rate\s*History", section, re.IGNORECASE)
    if next_heading:
        section = section[:next_heading.start()]

    match = re.search(r"\b1\s*G\b.{0,70}?(?:₹|INR\s*)?\s*([\d,]+(?:\.\d+)?)", section, re.IGNORECASE)
    if match:
        return _number(match.group(1))
    match = re.search(r"\b10\s*G\b.{0,70}?(?:₹|INR\s*)?\s*([\d,]+(?:\.\d+)?)", section, re.IGNORECASE)
    if match:
        value = _number(match.group(1))
        return value / 10 if value is not None else None
    return None


def parse_tanishq(html: str, url: str) -> dict[str, Any]:
    text = _plain_text(html)
    rate22 = _tanishq_rate(text, 22)
    rate24 = _tanishq_rate(text, 24)
    if rate22 is None and rate24 is None:
        raise ValueError("Tanishq page did not expose a current 22K/24K rate row")
    return {
        "retailer_id": "tanishq",
        "gold_22k_per_g": rate22,
        "gold_24k_per_g": rate24,
        "coin_10g_total": None,
        "making_charge_pct": None,
        "source": "Tanishq official published gold-rate page",
        "source_url": url,
        "timestamp": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
        "status": "automatic",
        "notes": "Published metal base rate; the page may default to 22K. Confirm displayed purity and store billing rate.",
    }


def _malabar_timestamp(text: str) -> str | None:
    match = re.search(
        r"Last\s*updated\s*:?\s*(\d{4}-\d{2}-\d{2})\s*,?\s*(\d{2}:\d{2}:\d{2})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    try:
        parsed = datetime.fromisoformat(f"{match.group(1)}T{match.group(2)}")
        return parsed.replace(tzinfo=ZoneInfo("Asia/Kolkata")).isoformat()
    except ValueError:
        return None


def parse_malabar(html: str, url: str) -> dict[str, Any]:
    text = _plain_text(html)
    rates: dict[int, float | None] = {22: None, 24: None}
    for purity in (22, 24):
        patterns = (
            rf"([\d,]+(?:\.\d+)?)\s*INR\s*/\s*gms\s*{purity}\s*k\b",
            rf"₹\s*([\d,]+(?:\.\d+)?)\s*/\s*g\s*\(\s*{purity}\s*kt\s*\)",
            rf"([\d,]+(?:\.\d+)?)\s*/\s*gms\s*{purity}\s*k\b",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                rates[purity] = _number(match.group(1))
                break
    if rates[22] is None and rates[24] is None:
        raise ValueError("Malabar page did not expose a current 22K/24K rate block")
    return {
        "retailer_id": "malabar",
        "gold_22k_per_g": rates[22],
        "gold_24k_per_g": rates[24],
        "coin_10g_total": None,
        "making_charge_pct": None,
        "source": "Malabar official live gold-rate page",
        "source_url": url,
        "timestamp": _malabar_timestamp(text) or datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
        "status": "automatic",
        "notes": "Published India/state gold rate; verify Maharashtra location selection and branch billing rate.",
    }


def parse_senco(html: str, url: str, city: str = "Pune") -> dict[str, Any]:
    text = _plain_text(html)
    match22 = re.search(
        r"₹\s*([\d,]+(?:\.\d+)?)\s*/\s*Gram\s*\(\s*22\s*ct\s*\)",
        text,
        re.IGNORECASE,
    )
    match24 = re.search(
        r"₹\s*([\d,]+(?:\.\d+)?)\s*/\s*Gram\s*\(\s*24\s*ct\s*\)",
        text,
        re.IGNORECASE,
    )
    if not match22:
        match22 = re.search(
            rf"22\s*K\s*gold\s*rate\s*in\s*{re.escape(city)}\s*is\s*₹\s*([\d,]+(?:\.\d+)?)\s*per\s*gram",
            text,
            re.IGNORECASE,
        )
    if not match24:
        match24 = re.search(
            rf"24\s*K\s*gold\s*rate\s*in\s*{re.escape(city)}\s*is\s*₹\s*([\d,]+(?:\.\d+)?)\s*per\s*gram",
            text,
            re.IGNORECASE,
        )
    rate22 = _number(match22.group(1)) if match22 else None
    rate24 = _number(match24.group(1)) if match24 else None
    if rate22 is None and rate24 is None:
        raise ValueError(f"Senco {city} page did not expose a current 22K/24K rate")
    return {
        "retailer_id": "senco",
        "gold_22k_per_g": rate22,
        "gold_24k_per_g": rate24,
        "coin_10g_total": None,
        "making_charge_pct": None,
        "source": f"Senco official {city} gold-rate page",
        "source_url": url,
        "timestamp": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
        "status": "automatic",
        "notes": "Official city-page rate; a published update time may not be present. Confirm current store billing rate.",
    }


def _sources(city: str) -> dict[str, tuple[str, Callable[[str, str], dict[str, Any]]]]:
    slug = re.sub(r"[^a-z0-9]+", "-", city.strip().lower()).strip("-") or "pune"
    return {
        "tanishq": (
            "https://www.tanishq.co.in/gold-rate.html?lang=en",
            parse_tanishq,
        ),
        "malabar": (
            "https://www.malabargoldanddiamonds.com/in/mh/en/live-gold-rate.html",
            parse_malabar,
        ),
        "senco": (
            f"https://sencogoldanddiamonds.com/gold-rate-today/{slug}",
            lambda html, url: parse_senco(html, url, city.strip() or "Pune"),
        ),
    }


async def _fetch_retailer(
    client: httpx.AsyncClient,
    retailer_id: str,
    url: str,
    parser: Callable[[str, str], dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    health = _HEALTH.setdefault(
        retailer_id,
        {
            "name": retailer_id,
            "status": "not_polled",
            "request_count": 0,
            "cache_hits": 0,
            "last_attempt_at": None,
            "last_success_at": None,
            "last_error": None,
        },
    )
    cached = _CACHE.get(retailer_id)
    now = time.monotonic()
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        health["status"] = "cached"
        health["cache_hits"] += 1
        return dict(cached[1]), dict(health)

    lock = _LOCKS.setdefault(retailer_id, asyncio.Lock())
    async with lock:
        cached = _CACHE.get(retailer_id)
        now = time.monotonic()
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            health["status"] = "cached"
            health["cache_hits"] += 1
            return dict(cached[1]), dict(health)

        health["last_attempt_at"] = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()
        health["request_count"] += 1
        try:
            response = await client.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
            response.raise_for_status()
            quote = parser(response.text, url)
            _CACHE[retailer_id] = (time.monotonic(), dict(quote))
            health["status"] = "ok"
            health["last_success_at"] = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()
            health["last_error"] = None
            return quote, dict(health)
        except Exception as exc:
            if isinstance(exc, httpx.HTTPStatusError):
                detail = f"HTTP {exc.response.status_code} from {exc.request.url.host}"
            elif isinstance(exc, httpx.RequestError):
                host = exc.request.url.host if exc.request else "retailer site"
                detail = f"{type(exc).__name__} contacting {host}"
            else:
                detail = f"{type(exc).__name__}: {str(exc)[:160]}"
            health["last_error"] = detail
            if cached:
                health["status"] = "stale"
                stale_quote = dict(cached[1])
                stale_quote["status"] = "stale"
                stale_quote["notes"] = f"{stale_quote.get('notes') or ''} Last request failed: {detail}"
                return stale_quote, dict(health)
            health["status"] = "error"
            return None, dict(health)


async def collect_automatic_retailer_quotes(
    client: httpx.AsyncClient,
    city: str = "Pune",
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Fetch public rate pages independently; a failure cannot block other retailers."""
    sources = _sources(city)
    results = await asyncio.gather(
        *(
            _fetch_retailer(client, retailer_id, url, parser)
            for retailer_id, (url, parser) in sources.items()
        ),
        return_exceptions=True,
    )
    quotes: dict[str, dict[str, Any]] = {}
    health: dict[str, dict[str, Any]] = {}
    for retailer_id, result in zip(sources, results):
        if isinstance(result, BaseException):
            health[retailer_id] = {
                "name": retailer_id,
                "status": "error",
                "last_error": f"{type(result).__name__}: retailer adapter failed",
            }
            continue
        quote, provider = result
        health[retailer_id] = provider
        if quote is not None:
            quotes[retailer_id] = quote
    return quotes, health


def clear_retailer_feed_cache() -> None:
    _CACHE.clear()
    _HEALTH.clear()
    _LOCKS.clear()
