from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

TROY_OUNCE_GRAMS = 31.1034768


def number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def percent_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current / previous - 1.0) * 100.0


def global_spot_inr_per_gram(xau_usd_oz: float, usd_inr: float) -> float:
    """Unadjusted global spot equivalent for one gram of 999 gold, INR."""
    return xau_usd_oz * usd_inr / TROY_OUNCE_GRAMS


def landed_reference_999_10g(
    xau_usd_oz: float,
    usd_inr: float,
    import_duty_pct: float,
    domestic_premium_pct: float = 0.0,
    local_cost_inr_per_10g: float = 0.0,
) -> float:
    """Indicative domestic parity model, not a customs assessment or dealer quote."""
    raw_10g = global_spot_inr_per_gram(xau_usd_oz, usd_inr) * 10.0
    duty_factor = 1.0 + import_duty_pct / 100.0
    premium_factor = 1.0 + domestic_premium_pct / 100.0
    return raw_10g * duty_factor * premium_factor + local_cost_inr_per_10g


def compare_pct(observed: float | None, reference: float | None) -> float | None:
    if observed is None or reference in (None, 0):
        return None
    return (observed / reference - 1.0) * 100.0


def coin_invoice_estimate(
    gold_rate_10g: float | None,
    weight_g: float,
    coin_premium_pct: float,
    fixed_fee_inr: float,
    gst_pct: float,
) -> dict[str, float] | None:
    if gold_rate_10g is None or weight_g <= 0:
        return None
    metal_value = gold_rate_10g * weight_g / 10.0
    premium = metal_value * coin_premium_pct / 100.0
    taxable_value = metal_value + premium + fixed_fee_inr
    gst = taxable_value * gst_pct / 100.0
    return {
        "metal_value_inr": round(metal_value, 2),
        "premium_inr": round(premium, 2),
        "fixed_fee_inr": round(fixed_fee_inr, 2),
        "taxable_value_inr": round(taxable_value, 2),
        "gst_inr": round(gst, 2),
        "total_inr": round(taxable_value + gst, 2),
    }


def build_recommendation(
    *,
    data_fresh: bool,
    ibja_999_10g: float | None,
    kalyan_24k_10g: float | None,
    kalyan_premium_pct: float | None,
    model_gap_pct: float | None,
    max_kalyan_premium_pct: float,
    watch_discount_pct: float,
) -> dict[str, Any]:
    reasons: list[str] = []
    if not data_fresh:
        return {
            "signal": "VERIFY DATA",
            "level": "warning",
            "score": None,
            "summary": "One or more key market inputs are missing or stale. Do not act on an apparent price gap until the quotes are refreshed.",
            "reasons": ["Check the source timestamps and obtain a live showroom quote."],
        }
    if ibja_999_10g is None or kalyan_24k_10g is None or kalyan_premium_pct is None:
        return {
            "signal": "WAIT FOR QUOTES",
            "level": "neutral",
            "score": None,
            "summary": "A usable IBJA 999 benchmark and Kalyan 24K quote are both needed to judge the retail premium.",
            "reasons": ["Add a manual quote or connect the relevant source."],
        }

    if kalyan_premium_pct <= 0:
        score = 90
        reasons.append(f"Kalyan's published 24K rate is {abs(kalyan_premium_pct):.2f}% at or below the IBJA 999 reference.")
    elif kalyan_premium_pct <= max_kalyan_premium_pct:
        score = 75
        reasons.append(f"Kalyan's premium is {kalyan_premium_pct:.2f}%, within your {max_kalyan_premium_pct:.2f}% tolerance.")
    else:
        score = max(10, int(75 - (kalyan_premium_pct - max_kalyan_premium_pct) * 25))
        reasons.append(f"Kalyan is {kalyan_premium_pct:.2f}% above IBJA; ask for the all-inclusive coin quote and compare another seller.")

    if model_gap_pct is not None:
        if abs(model_gap_pct) > 3:
            score = min(score, 45)
            reasons.append("The domestic benchmark differs materially from the simplified import-parity model; review duty/premium assumptions before interpreting it as an opportunity.")
        elif model_gap_pct < -watch_discount_pct:
            score = min(100, score + 5)
            reasons.append("IBJA is below the modelled import-parity reference by more than your watch threshold.")
        else:
            reasons.append("The IBJA-to-model spread is within the configured monitoring range.")

    if kalyan_premium_pct > max_kalyan_premium_pct:
        signal, level = "NEGOTIATE / COMPARE", "warning"
        summary = "The available Kalyan quote is above your chosen premium tolerance versus IBJA. Compare the final bill with another BIS-authorised seller before buying."
    elif kalyan_premium_pct <= 0:
        signal, level = "FAVOURABLE QUOTE", "good"
        summary = "The Kalyan published 24K rate is at or below the IBJA reference. Confirm the live billing rate, coin premium, GST and buyback terms before purchase."
    else:
        signal, level = "FAIR — VERIFY BILL", "neutral"
        summary = "The Kalyan published rate is within your premium tolerance. The final coin premium and buyback spread still determine value."

    return {"signal": signal, "level": level, "score": score, "summary": summary, "reasons": reasons}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
