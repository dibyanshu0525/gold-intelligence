from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import httpx
from bs4 import BeautifulSoup

from .config import ENV
from .pricing import TROY_OUNCE_GRAMS

USER_AGENT = "GoldIntelligence/1.0 (+local personal research dashboard)"


def _iso_from_epoch(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _timestamp(data: dict[str, Any]) -> str | None:
    value = data.get("timestamp") or data.get("updated_at") or data.get("last_updated")
    if isinstance(value, (int, float)):
        return _iso_from_epoch(value)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            return None
    return None


def point(value: float | None, unit: str, source: str, status: str, timestamp: str | None = None, note: str | None = None) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "source": source,
        "status": status,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "note": note,
    }


class MetalsDevProvider:
    """Metals.Dev connector. It keeps the vendor API key on the server."""

    base_url = "https://api.metals.dev/v1"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not ENV.metals_dev_api_key:
            raise RuntimeError("METALS_DEV_API_KEY is not configured")
        params = {**params, "api_key": ENV.metals_dev_api_key}
        response = await self.client.get(f"{self.base_url}/{path}", params=params)
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.is_error:
            message = body.get("error_message") or body.get("message") if isinstance(body, dict) else None
            code = body.get("error_code") if isinstance(body, dict) else None
            suffix = f" (code {code})" if code is not None else ""
            raise RuntimeError(f"Metals.Dev HTTP {response.status_code}{suffix}: {message or 'request rejected'}")
        if not isinstance(body, dict):
            raise RuntimeError("Metals.Dev returned a non-object JSON response")
        if body.get("status") == "failure":
            code = body.get("error_code")
            suffix = f" (code {code})" if code is not None else ""
            raise RuntimeError(f"Metals.Dev returned failure{suffix}: {body.get('error_message') or 'unknown provider error'}")
        return body

    async def spot(self) -> dict[str, Any]:
        body = await self._get("metal/spot", {"metal": "gold", "currency": "USD"})
        rate = body.get("rate") or {}
        value = rate.get("price") or body.get("price")
        return {
            "xau_usd_oz": point(float(value) if value is not None else None, "USD / troy oz", "Metals.Dev spot", "live" if value is not None else "unavailable", _timestamp(body), "Provider states up to 60-second delay; market data is not an exchange execution quote."),
            "spot_change_pct": rate.get("change_percent"),
            "spot_day_high": rate.get("high"),
            "spot_day_low": rate.get("low"),
        }

    async def fx(self) -> dict[str, Any]:
        body = await self._get("currencies", {"base": "USD"})
        currencies = body.get("currencies") or body.get("rates") or {}
        value = currencies.get("INR") or currencies.get("inr")
        return {
            "usd_inr": point(float(value) if value is not None else None, "INR per USD", "Metals.Dev currency feed", "live" if value is not None else "unavailable", _timestamp(body), "Provider states up to 120-second delay."),
        }

    async def authority(self, authority: str) -> dict[str, Any]:
        body = await self._get("metal/authority", {"authority": authority, "currency": "INR", "unit": "toz"})
        rates = body.get("rates") or body.get("metals") or {}
        ts = _timestamp(body)
        prefix = authority.lower()
        current = rates.get(f"{prefix}_gold") or rates.get("gold")
        am = rates.get(f"{prefix}_gold_am") or rates.get("gold_am")
        pm = rates.get(f"{prefix}_gold_pm") or rates.get("gold_pm")
        selected = pm or current or am
        def normalize_10g(raw: Any) -> float | None:
            if raw is None:
                return None
            amount = float(raw)
            # Authority endpoint returns INR per troy ounce; convert to INR per 10g.
            return amount * 10.0 / TROY_OUNCE_GRAMS

        selected_10g = normalize_10g(selected)
        am_10g = normalize_10g(am)
        pm_10g = normalize_10g(pm)
        return {
            f"{prefix}_999_10g": point(selected_10g, "INR / 10g", f"Metals.Dev {authority.upper()} authority feed", "live" if selected_10g is not None else "unavailable", ts, "Requested as INR/g and normalized to 10g; confirm feed schema and contract basis on first use."),
            f"{prefix}_am_10g": am_10g,
            f"{prefix}_pm_10g": pm_10g,
        }


class AlternativeProvider:
    """Optional vendor fallback when Metals.Dev is not configured."""

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def goldapi_spot(self) -> dict[str, Any] | None:
        if not ENV.goldapi_key:
            return None
        response = await self.client.get(
            "https://www.goldapi.io/api/XAU/USD",
            headers={"x-access-token": ENV.goldapi_key, "User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        body = response.json()
        price = body.get("price")
        return {"xau_usd_oz": point(float(price) if price is not None else None, "USD / troy oz", "GoldAPI.io", "live" if price is not None else "unavailable", _timestamp(body))}

    async def twelve_data_quote(self, symbol: str) -> dict[str, Any] | None:
        if not ENV.twelve_data_api_key:
            return None
        response = await self.client.get(
            "https://api.twelvedata.com/price",
            params={"symbol": symbol, "apikey": ENV.twelve_data_api_key},
        )
        response.raise_for_status()
        body = response.json()
        value = body.get("price")
        if value is None:
            raise RuntimeError(body.get("message") or f"Twelve Data did not return {symbol}")
        return {"value": float(value), "timestamp": datetime.now(timezone.utc).isoformat()}


async def scrape_ibja(client: httpx.AsyncClient) -> dict[str, Any]:
    """Best-effort fallback parser for the public IBJA AM/PM webpage.

    This is not an official API. A licensed/official IBJA API should be used for
    transaction-critical or commercial applications.
    """
    response = await client.get(ENV.ibja_url, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    captured = datetime.now(timezone.utc).isoformat()
    for row in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
        joined = " ".join(cells)
        if "Gold 999" not in joined:
            continue
        nums: list[float] = []
        for cell in cells:
            found = re.findall(r"(?<!\w)[\d,]+(?:\.\d+)?", cell)
            for item in found:
                value = float(item.replace(",", ""))
                if value > 1000:
                    nums.append(value)
        # Published IBJA table is per 10g. Some page renderings may include the label cell only.
        if nums:
            am = nums[0]
            pm = nums[1] if len(nums) > 1 else None
            chosen = pm or am
            return {
                "ibja_999_10g": point(chosen, "INR / 10g", "IBJA public webpage (scraped fallback)", "delayed", captured, "Public-page fallback; not the licensed IBJA API. Table values are per 10g and exclude GST/making charges."),
                "ibja_am_10g": am,
                "ibja_pm_10g": pm,
            }
    # Text fallback for pages whose rows are not emitted as HTML table rows.
    text = soup.get_text(" ", strip=True)
    match = re.search(r"Gold\s*999\s*([\d,]+)\s*([\d,]+)?", text, re.IGNORECASE)
    if match:
        am = float(match.group(1).replace(",", ""))
        pm = float(match.group(2).replace(",", "")) if match.group(2) else None
        return {
            "ibja_999_10g": point(pm or am, "INR / 10g", "IBJA public webpage (scraped fallback)", "delayed", captured, "Public-page fallback; confirm session and timestamp."),
            "ibja_am_10g": am,
            "ibja_pm_10g": pm,
        }
    raise RuntimeError("Could not locate Gold 999 AM/PM row on the IBJA page")


async def scrape_kalyan(client: httpx.AsyncClient) -> dict[str, Any]:
    """Best-effort parser for Kalyan's official public rate page.

    Kalyan states that the rate at billing prevails. This page may be national-level;
    the dashboard labels it accordingly and recommends a Pune-branch confirmation.
    """
    response = await client.get(ENV.kalyan_url, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    ts = datetime.now(timezone.utc).isoformat()

    def find_rate(patterns: list[str]) -> float | None:
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return float(match.group(1).replace(",", ""))
        return None

    # Kalyan's rendered text commonly publishes both 10g and per-gram prices.
    rate_24_10 = find_rate([
        r"10g\s+of\s+24K\s+Gold\s+in\s+Indian\s+Rupee\s*₹?\s*([\d,]+)",
        r"24k\s+\|\s*₹?\s*([\d,]+)\s*\|",
    ])
    rate_22_10 = find_rate([
        r"10g\s+of\s+22K\s+Gold\s+in\s+Indian\s+Rupee\s*₹?\s*([\d,]+)",
        r"22k\s+\|\s*₹?\s*([\d,]+)\s*\|",
    ])
    if rate_24_10 is None:
        per_g = find_rate([r"Gold\s+Rate\s+in\s+India\s+for\s+1\s+gram\s+24\s+is\s+₹\s*([\d,]+)"])
        rate_24_10 = per_g * 10 if per_g else None
    if rate_22_10 is None:
        per_g = find_rate([r"Gold\s+Rate\s+in\s+India\s+for\s+1\s+gram\s+22\s+is\s+₹\s*([\d,]+)"])
        rate_22_10 = per_g * 10 if per_g else None
    if rate_24_10 is None and rate_22_10 is None:
        raise RuntimeError("Could not parse 24K/22K rate from Kalyan's page")
    return {
        "kalyan_24k_10g": point(rate_24_10, "INR / 10g", "Kalyan official published rate page", "delayed", ts, "Best-effort website scrape; page may be national-level. Kalyan says billing-time rate prevails."),
        "kalyan_22k_10g": point(rate_22_10, "INR / 10g", "Kalyan official published rate page", "delayed", ts, "Confirm with the Pune showroom before purchase."),
    }


async def fetch_open_fx_fallback(client: httpx.AsyncClient) -> dict[str, Any] | None:
    """Public daily FX fallback. Never labelled as live."""
    response = await client.get("https://open.er-api.com/v6/latest/USD", headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    body = response.json()
    rate = (body.get("rates") or {}).get("INR")
    if rate is None:
        return None
    updated = body.get("time_last_update_utc")
    ts = None
    if updated:
        try:
            ts = datetime.strptime(updated, "%a, %d %b %Y %H:%M:%S %z").astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    return {"usd_inr": point(float(rate), "INR per USD", "open.er-api.com daily reference fallback", "delayed", ts, "Daily reference rate, not an intraday executable FX quote.")}
