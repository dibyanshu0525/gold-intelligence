import pytest

from app.pricing import (
    build_recommendation,
    coin_invoice_estimate,
    compare_pct,
    global_spot_inr_per_gram,
    landed_reference_999_10g,
)


def test_xau_usd_to_inr_per_gram_conversion():
    # Example inputs only; not a current-market quote.
    result = global_spot_inr_per_gram(2000, 83)
    assert result == pytest.approx(2000 * 83 / 31.1034768)


def test_landed_reference_includes_duty_and_premium():
    raw_10g = global_spot_inr_per_gram(2000, 83) * 10
    result = landed_reference_999_10g(2000, 83, 15, 0.5, 10)
    assert result == pytest.approx(raw_10g * 1.15 * 1.005 + 10)


def test_compare_pct():
    assert compare_pct(101, 100) == pytest.approx(1.0)
    assert compare_pct(None, 100) is None
    assert compare_pct(100, 0) is None


def test_coin_invoice_estimate_includes_premium_and_gst():
    result = coin_invoice_estimate(100000, 10, 1, 100, 3)
    assert result is not None
    assert result["metal_value_inr"] == 100000
    assert result["premium_inr"] == 1000
    assert result["taxable_value_inr"] == 101100
    assert result["gst_inr"] == pytest.approx(3033)
    assert result["total_inr"] == pytest.approx(104133)


def test_recommendation_blocks_when_data_stale():
    result = build_recommendation(
        data_fresh=False,
        ibja_999_10g=100000,
        kalyan_24k_10g=100000,
        kalyan_premium_pct=0,
        model_gap_pct=0,
        max_kalyan_premium_pct=0.75,
        watch_discount_pct=0.5,
    )
    assert result["signal"] == "VERIFY DATA"


def test_recommendation_flags_high_retail_premium():
    result = build_recommendation(
        data_fresh=True,
        ibja_999_10g=100000,
        kalyan_24k_10g=102000,
        kalyan_premium_pct=2.0,
        model_gap_pct=0.5,
        max_kalyan_premium_pct=0.75,
        watch_discount_pct=0.5,
    )
    assert result["signal"] == "NEGOTIATE / COMPARE"


def test_retailer_directory_includes_major_channels_and_separates_missing_quotes():
    from app.retailers import retailer_directory, RETAILER_BY_ID

    data = retailer_directory(
        "Pune",
        [
            {
                "retailer_id": "tanishq", "city": "Pune", "gold_22k_per_g": 11500,
                "gold_24k_per_g": 12500, "coin_10g_total": 129000,
                "making_charge_pct": 8, "source": "Pune showroom", "source_url": None,
                "notes": None, "timestamp": "2026-11-23T10:00:00+00:00", "status": "manual",
            }
        ],
        {
            "kalyan_24k_10g": {"value": 126000, "source": "Kalyan public rate", "status": "delayed", "timestamp": "2026-11-23T10:00:00+00:00"},
            "kalyan_22k_10g": {"value": 115500, "source": "Kalyan public rate", "status": "delayed", "timestamp": "2026-11-23T10:00:00+00:00"},
        },
    )
    assert {"kalyan", "tanishq", "malabar", "joyalukkas", "pngadgilandsons", "mmtcpamp", "augmont"}.issubset(RETAILER_BY_ID)
    assert data["summary"]["retailer_count"] >= 20
    assert data["summary"]["quoted_count"] == 2
    rows = {row["id"]: row for row in data["retailers"]}
    assert rows["kalyan"]["gold_24k_per_g"] == 12600
    assert rows["tanishq"]["gold_22k_per_g"] == 11500
    assert rows["malabar"]["quote_status"] == "not_entered"
    assert data["summary"]["gold_24k_lowest"] == "tanishq"
