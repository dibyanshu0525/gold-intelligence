import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.market_data import (
    _cached_fetch,
    clear_provider_cache,
    parse_frankfurter,
    parse_gold_api_com,
    parse_goldapi_dev,
    parse_goldapi_dev_inr,
    parse_goldprice_dev,
    parse_xaus,
    collect_multi_source_market_data,
)
from app.pricing import TROY_OUNCE_GRAMS


def test_parse_xaus_combines_spot_fx_and_inr_equivalent():
    data = parse_xaus({
        "xau": {"price": 84000.0, "currency": "INR", "unit": "troy_oz"},
        "spot_usd_oz": 3000.0,
        "fx_rate": 84.0,
        "updated_at": "2026-11-23T10:00:00Z",
        "price_as_of": "2026-11-23T09:59:00Z",
        "data_state": {"status": "fresh", "as_of": "2026-11-23T09:59:00Z"},
        "fx_stale": False,
    })
    assert data["xau_usd"]["value"] == 3000.0
    assert data["usd_inr"]["value"] == 84.0
    assert data["xau_inr_10g"]["value"] == pytest.approx(84000 * 10 / TROY_OUNCE_GRAMS)
    assert data["xau_usd"]["status"] == "live"


def test_parse_xaus_never_labels_upstream_stale_price_as_live():
    data = parse_xaus({
        "xau": {"price": 84000.0, "currency": "INR", "unit": "troy_oz"},
        "spot_usd_oz": 3000.0,
        "fx_rate": 84.0,
        "updated_at": "2026-11-23T10:00:00Z",
        "price_as_of": "2026-11-23T09:00:00Z",
        "data_state": {"status": "stale", "as_of": "2026-11-23T09:00:00Z", "age_seconds": 3600},
        "stale": True,
        "fx_stale": True,
    })
    assert data["xau_usd"]["status"] == "stale"
    assert data["usd_inr"]["status"] == "delayed"


def test_parse_goldapi_dev_and_inr_quote():
    data = parse_goldapi_dev(
        {"price": 3000.0, "gram": 96.45, "updatedAt": "2026-11-23T10:00:00Z"},
        {"rates": {"INR": 84.0}, "_server_time": "2026-11-23T10:00:02Z"},
    )
    assert data["xau_usd"]["value"] == 3000.0
    assert data["usd_inr"]["value"] == 84.0
    inr = parse_goldapi_dev_inr({"gram": 8210.5, "updatedAt": "2026-11-23T10:00:00Z"})
    assert inr["xau_inr_10g"]["value"] == pytest.approx(82105.0)


def test_parse_goldprice_dev_uses_delayed_status_and_converts_ounce_to_10g():
    data = parse_goldprice_dev({
        "price": str(84000.0),
        "computed_at": "2026-11-23T09:45:00Z",
        "is_stale": False,
    })
    assert data["xau_inr_10g"]["status"] == "delayed"
    assert data["xau_inr_10g"]["value"] == pytest.approx(84000 * 10 / TROY_OUNCE_GRAMS)


def test_parse_frankfurter_marks_daily_fx_as_delayed():
    data = parse_frankfurter({"base": "USD", "quote": "INR", "date": "2026-11-23", "rate": 84.0})
    assert data["usd_inr"]["value"] == 84.0
    assert data["usd_inr"]["status"] == "delayed"
    assert data["usd_inr"]["timestamp"].startswith("2026-11-23")


def test_provider_cache_reuses_data_and_reports_cache_hit():
    async def run():
        clear_provider_cache()
        calls = {"count": 0}

        async def loader():
            calls["count"] += 1
            return {"sample": {"value": 12.0}}

        first, health1 = await _cached_fetch("unit-test", 60, True, loader)
        second, health2 = await _cached_fetch("unit-test", 60, True, loader)
        assert first == second
        assert calls["count"] == 1
        assert health1["status"] == "ok"
        assert health2["status"] == "cached"
        assert health2["cache_hits"] == 1

    asyncio.run(run())


def test_provider_cache_returns_stale_copy_after_upstream_failure():
    async def run():
        clear_provider_cache()

        async def good_loader():
            return {"sample": {"value": 12.0, "status": "live", "note": "source"}}

        async def bad_loader():
            raise RuntimeError("provider offline")

        await _cached_fetch("unit-stale", 0, True, good_loader)
        stale, health = await _cached_fetch("unit-stale", 0, True, bad_loader)
        assert stale["sample"]["value"] == 12.0
        assert stale["sample"]["status"] == "stale"
        assert "provider offline" in stale["sample"]["note"]
        assert health["status"] == "stale"

    asyncio.run(run())


def _test_env(**overrides):
    values = {
        "xaus_enabled": True,
        "gold_api_com_enabled": False,
        "goldapi_dev_key": "",
        "goldprice_enabled": False,
        "goldprice_api_key": "",
        "frankfurter_enabled": False,
        "twelve_data_api_key": "",
        "metals_dev_api_key": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_multi_source_orchestrator_selects_keyless_xaus(monkeypatch):
    from app import market_data

    async def run():
        clear_provider_cache()
        monkeypatch.setattr(market_data, "ENV", _test_env())
        now = datetime.now(timezone.utc).isoformat()

        async def handler(request):
            assert request.url.host == "xaus.com"
            return httpx.Response(200, json={
                "xau": {"price": 270000.0, "currency": "INR", "unit": "troy_oz"},
                "spot_usd_oz": 3100.0,
                "fx_rate": 87.0,
                "updated_at": now,
                "price_as_of": now,
                "data_state": {"status": "fresh", "as_of": now},
                "fx_stale": False,
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await collect_multi_source_market_data(client)

        assert result["selected_provider"] == {"xau_usd": "xaus", "usd_inr": "xaus"}
        assert result["selected"]["xau_usd"]["value"] == 3100.0
        assert result["selected"]["usd_inr"]["value"] == 87.0
        assert result["provider_health"]["xaus"]["request_count"] == 1
        assert result["provider_health"]["goldapi_dev"]["status"] == "disabled"

    asyncio.run(run())


def test_multi_source_orchestrator_falls_back_to_goldapi_dev(monkeypatch):
    from app import market_data

    async def run():
        clear_provider_cache()
        monkeypatch.setattr(market_data, "ENV", _test_env(xaus_enabled=False, goldapi_dev_key="test-key"))
        now = datetime.now(timezone.utc).isoformat()
        seen = []

        async def handler(request):
            seen.append(request.url.path)
            if request.url.path.endswith("/price/XAU/USD"):
                return httpx.Response(200, json={"price": 3100.0, "updatedAt": now})
            if request.url.path.endswith("/rates"):
                return httpx.Response(200, json={"rates": {"INR": 87.0}, "_server_time": now})
            if request.url.path.endswith("/price/XAU/INR/24"):
                return httpx.Response(200, json={"gram": 7560.0, "updatedAt": now})
            raise AssertionError(f"Unexpected URL: {request.url}")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await collect_multi_source_market_data(client)

        assert result["selected_provider"]["xau_usd"] == "goldapi_dev"
        assert result["selected_provider"]["usd_inr"] == "goldapi_dev"
        assert result["selected"]["xau_usd"]["value"] == 3100.0
        assert result["selected"]["usd_inr"]["value"] == 87.0
        assert result["provider_health"]["goldapi_dev"]["request_count"] == 3
        assert len(seen) == 3

    asyncio.run(run())


def test_parse_gold_api_com_converts_usd_and_inr_spot_quotes():
    data = parse_gold_api_com(
        {"price": 3100.0, "currency": "USD", "updatedAt": "2026-11-23T10:00:00Z"},
        {"price": 270000.0, "currency": "INR", "updatedAt": "2026-11-23T10:00:15Z"},
    )
    assert data["xau_usd"]["value"] == 3100.0
    assert data["xau_inr_10g"]["value"] == pytest.approx(270000.0 * 10 / TROY_OUNCE_GRAMS)
    assert data["xau_inr_10g"]["status"] == "live"


def test_multi_source_orchestrator_uses_gold_api_com_fallback(monkeypatch):
    from app import market_data

    async def run():
        clear_provider_cache()
        monkeypatch.setattr(market_data, "ENV", _test_env(xaus_enabled=False, gold_api_com_enabled=True))
        now = datetime.now(timezone.utc).isoformat()

        async def handler(request):
            if request.url.path.endswith("/price/XAU/USD"):
                return httpx.Response(200, json={"price": 3100.0, "currency": "USD", "updatedAt": now})
            if request.url.path.endswith("/price/XAU/INR"):
                return httpx.Response(200, json={"price": 270000.0, "currency": "INR", "updatedAt": now})
            raise AssertionError(f"Unexpected URL: {request.url}")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await collect_multi_source_market_data(client)

        assert result["selected_provider"]["xau_usd"] == "gold_api_com"
        assert result["selected"]["xau_usd"]["value"] == 3100.0
        assert result["provider_health"]["gold_api_com"]["request_count"] == 2
        assert "gold_api_com" in result["cross_checks"]

    asyncio.run(run())


def test_goldprice_adapter_uses_current_single_symbol_spot_endpoint(monkeypatch):
    from app import market_data

    async def run():
        clear_provider_cache()
        monkeypatch.setattr(
            market_data,
            "ENV",
            _test_env(xaus_enabled=False, goldprice_enabled=True),
        )
        now = datetime.now(timezone.utc).isoformat()
        seen = []

        async def handler(request):
            seen.append((request.url.path, dict(request.url.params)))
            assert request.url.host == "api.goldprice.dev"
            return httpx.Response(200, json={
                "symbol": "XAU-INR-SPOT",
                "quote_currency": "INR",
                "unit": "troy_ounce",
                "price": "270000",
                "computed_at": now,
                "is_stale": False,
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await collect_multi_source_market_data(client)

        assert seen == [("/v1/spot/XAU", {"currency": "INR", "include": "sources"})]
        assert result["cross_checks"]["goldprice_dev"]["status"] == "delayed"
        assert result["cross_checks"]["goldprice_dev"]["value"] == pytest.approx(270000 * 10 / TROY_OUNCE_GRAMS)

    asyncio.run(run())
