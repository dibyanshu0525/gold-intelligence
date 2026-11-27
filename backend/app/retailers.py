from __future__ import annotations

from typing import Any

# National, regional/Pune-relevant and bullion/coin channels. Public links are
# provided for quote verification. Best-effort automatic adapters cover retailers
# with public machine-readable rates; other prices require a dated verified quote.
RETAILERS: list[dict[str, Any]] = [
    {"id": "kalyan", "name": "Kalyan Jewellers", "segment": "Jewellery chain", "coverage": "Pan-India", "website": "https://www.kalyanjewellers.net/", "rate_url": "https://www.kalyanjewellers.net/gold-rate/Gold-Rate", "coin_url": "https://www.candere.com/", "feed": "automatic_kalyan", "notes": "Existing Kalyan India public-rate adapter; confirm Pune billing quote."},
    {"id": "tanishq", "name": "Tanishq", "segment": "Jewellery chain", "coverage": "Pan-India", "website": "https://www.tanishq.co.in/", "rate_url": "https://www.tanishq.co.in/gold-rate.html", "coin_url": "https://www.tanishq.co.in/", "feed": "automatic_tanishq", "notes": "Official rate page publishes 18K/22K/24K and historical rates."},
    {"id": "malabar", "name": "Malabar Gold & Diamonds", "segment": "Jewellery chain", "coverage": "Pan-India", "website": "https://www.malabargoldanddiamonds.com/", "rate_url": "https://www.malabargoldanddiamonds.com/in/mh/en/live-gold-rate.html", "coin_url": "https://www.malabargoldanddiamonds.com/", "feed": "automatic_malabar", "notes": "One-India-one-gold-rate claim; check current state/location selection."},
    {"id": "joyalukkas", "name": "Joyalukkas", "segment": "Jewellery chain", "coverage": "Pan-India", "website": "https://www.joyalukkas.in/", "rate_url": "https://www.joyalukkas.in/goldrate", "coin_url": "https://www.joyalukkas.in/", "feed": "manual_quote", "notes": "Official page distinguishes retail-store and online-store rates."},
    {"id": "pngadgilandsons", "name": "PN Gadgil & Sons", "segment": "Jewellery chain", "coverage": "Maharashtra / Pune", "website": "https://pngadgilandsons.com/", "rate_url": "https://pngadgilandsons.com/", "coin_url": "https://pngadgilandsons.com/online-store/", "feed": "manual_quote", "notes": "Separate legal/retail business from PNG Jewellers; confirm branch quote and purity basis."},
    {"id": "pngjewellers", "name": "PNG Jewellers", "segment": "Jewellery chain", "coverage": "Maharashtra / Pune", "website": "https://www.onlinepng.com/", "rate_url": "https://www.onlinepng.com/", "coin_url": "https://www.onlinepng.com/", "feed": "manual_quote", "notes": "Online PNG lists gold bullion/coin products and metal rates."},
    {"id": "senco", "name": "Senco Gold & Diamonds", "segment": "Jewellery chain", "coverage": "Pan-India / selected cities", "website": "https://sencogoldanddiamonds.com/", "rate_url": "https://sencogoldanddiamonds.com/gold-rate-today/pune", "coin_url": "https://sencogoldanddiamonds.com/", "feed": "automatic_senco", "notes": "City-specific rate pages; use Pune page rather than a national comparison."},
    {"id": "reliance", "name": "Reliance Jewels", "segment": "Jewellery chain", "coverage": "Pan-India", "website": "https://www.reliancejewels.com/", "rate_url": "https://www.reliancejewels.com/", "coin_url": "https://www.reliancejewels.com/gold-accessories/", "feed": "manual_quote", "notes": "Homepage has a time-stamped gold-rate widget; check its update time."},
    {"id": "candere", "name": "Candere by Kalyan", "segment": "Online jewellery", "coverage": "Online / Pan-India", "website": "https://www.candere.com/", "rate_url": "https://www.candere.com/", "coin_url": "https://www.candere.com/", "feed": "manual_quote", "notes": "Online-first jewellery retailer; product price may include design and product premiums."},
    {"id": "caratlane", "name": "CaratLane (A Tata Product)", "segment": "Online + stores", "coverage": "Pan-India", "website": "https://www.caratlane.com/", "rate_url": "https://www.caratlane.com/", "coin_url": "https://www.caratlane.com/", "feed": "manual_quote", "notes": "Gold-rate link is available on its site; compare product checkout, not only metal rate."},
    {"id": "bluestone", "name": "BlueStone", "segment": "Online + stores", "coverage": "Pan-India", "website": "https://www.bluestone.com/", "rate_url": "https://www.bluestone.com/", "coin_url": "https://www.bluestone.com/", "feed": "manual_quote", "notes": "Product-specific price breakup may be more useful than a generic rate."},
    {"id": "orra", "name": "ORRA", "segment": "Jewellery chain", "coverage": "Pan-India", "website": "https://www.orra.co.in/", "rate_url": "https://www.orra.co.in/", "coin_url": "https://www.orra.co.in/", "feed": "manual_quote", "notes": "Obtain a dated branch quotation."},
    {"id": "indriya", "name": "Indriya by Aditya Birla", "segment": "Jewellery chain", "coverage": "Selected Indian cities", "website": "https://www.indriya.com/", "rate_url": "https://www.indriya.com/", "coin_url": "https://www.indriya.com/jewellery", "feed": "manual_quote", "notes": "Has 22K and 24K product categories; request a store-level rate."},
    {"id": "tbz", "name": "TBZ – The Original", "segment": "Jewellery chain", "coverage": "India", "website": "https://www.tbztheoriginal.com/", "rate_url": "https://www.tbztheoriginal.com/", "coin_url": "https://www.tbztheoriginal.com/", "feed": "manual_quote", "notes": "Branch quotation required."},
    {"id": "grt", "name": "GRT Jewellers", "segment": "Jewellery chain", "coverage": "South India / India", "website": "https://www.grtjewels.com/", "rate_url": "https://www.grtjewels.com/", "coin_url": "https://www.grtjewels.com/", "feed": "manual_quote", "notes": "City and store may affect the applicable rate."},
    {"id": "bhima", "name": "Bhima Jewels", "segment": "Jewellery chain", "coverage": "South / West India", "website": "https://www.bhimagold.com/", "rate_url": "https://www.bhimagold.com/gold-rates", "coin_url": "https://www.bhimagold.com/", "feed": "manual_quote", "notes": "Official page distinguishes online rates from store rates; verify which applies."},
    {"id": "josalukkas", "name": "Jos Alukkas", "segment": "Jewellery chain", "coverage": "India", "website": "https://www.josalukkasonline.com/", "rate_url": "https://www.josalukkasonline.com/", "coin_url": "https://www.josalukkasonline.com/", "feed": "manual_quote", "notes": "Rate pages can be location-specific."},
    {"id": "whp", "name": "Waman Hari Pethe Jewellers", "segment": "Regional jeweller", "coverage": "Maharashtra / Pune", "website": "https://www.wamanharipethesons.com/", "rate_url": "https://www.wamanharipethesons.com/", "coin_url": "https://www.wamanharipethesons.com/", "feed": "manual_quote", "notes": "Local Maharashtra comparison; get an exact Pune branch quote."},
    {"id": "ranka", "name": "Ranka Jewellers", "segment": "Regional jeweller", "coverage": "Pune / Maharashtra", "website": "https://rankajewellers.com/", "rate_url": "https://rankajewellers.com/", "coin_url": "https://rankajewellers.com/", "feed": "manual_quote", "notes": "Website explicitly warns store rates may vary from website metal rates."},
    {"id": "pcchandra", "name": "PC Chandra Jewellers", "segment": "Jewellery chain", "coverage": "East / North India", "website": "https://pcchandraindia.com/", "rate_url": "https://pcchandraindia.com/", "coin_url": "https://pcchandraindia.com/", "feed": "manual_quote", "notes": "Branch quotation required; location-specific."},
    {"id": "mmtcpamp", "name": "MMTC-PAMP", "segment": "Bullion / minted coins", "coverage": "Online / Pan-India", "website": "https://www.mmtcpamp.com/", "rate_url": "https://www.mmtcpamp.com/", "coin_url": "https://www.mmtcpamp.com/shop", "feed": "manual_quote", "notes": "999.9+ minted coins/bars; compare exact 10g product checkout total and buyback rules."},
    {"id": "augmont", "name": "Augmont", "segment": "Bullion / minted coins", "coverage": "Online / Pan-India", "website": "https://augmont.com/", "rate_url": "https://augmont.com/", "coin_url": "https://augmont.com/shop/gold-coin", "feed": "manual_quote", "notes": "Lists 999-purity coins; compare exact product weight, delivered price and sell-back spread."},
    {"id": "safegold", "name": "SafeGold", "segment": "Digital gold / delivery", "coverage": "Online / Pan-India", "website": "https://www.safegold.com/", "rate_url": "https://www.safegold.com/", "coin_url": "https://www.safegold.com/", "feed": "manual_quote", "notes": "Digital gold is not the same as immediately delivered physical bullion; check spread, storage, delivery and counterparty terms."},
]

RETAILER_BY_ID = {item["id"]: item for item in RETAILERS}


def retailer_directory(
    city: str,
    quotes: list[dict[str, Any]],
    kalyan_source: dict[str, Any] | None = None,
    automatic_quotes: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    quote_map = {item["retailer_id"]: item for item in quotes}
    automatic_quotes = automatic_quotes or {}
    output: list[dict[str, Any]] = []
    for item in RETAILERS:
        # A verified city/showroom quote takes precedence over a public web rate.
        quote = quote_map.get(item["id"]) or automatic_quotes.get(item["id"])
        if item["id"] == "kalyan" and not quote and kalyan_source:
            q24 = kalyan_source.get("kalyan_24k_10g") or {}
            q22 = kalyan_source.get("kalyan_22k_10g") or {}
            if q24.get("value") is not None or q22.get("value") is not None:
                quote = {
                    "retailer_id": "kalyan",
                    "city": city,
                    "gold_22k_per_g": float(q22["value"]) / 10 if q22.get("value") is not None else None,
                    "gold_24k_per_g": float(q24["value"]) / 10 if q24.get("value") is not None else None,
                    "coin_10g_total": None,
                    "making_charge_pct": None,
                    "source": q24.get("source") or q22.get("source") or "Kalyan India public-rate feed",
                    "source_url": item["rate_url"],
                    "timestamp": q24.get("timestamp") or q22.get("timestamp"),
                    "status": q24.get("status") or q22.get("status") or "unavailable",
                    "notes": "National/online published base rate; confirm the Pune showroom billing quote.",
                }
        row = {**item, "quote": quote}
        if quote:
            row["gold_22k_per_g"] = quote.get("gold_22k_per_g")
            row["gold_24k_per_g"] = quote.get("gold_24k_per_g")
            row["coin_10g_total"] = quote.get("coin_10g_total")
            row["making_charge_pct"] = quote.get("making_charge_pct")
            row["quote_status"] = quote.get("status", "manual")
            row["quote_timestamp"] = quote.get("timestamp")
            row["quote_source"] = quote.get("source")
        else:
            row.update({"gold_22k_per_g": None, "gold_24k_per_g": None, "coin_10g_total": None,
                        "making_charge_pct": None, "quote_status": "not_entered", "quote_timestamp": None,
                        "quote_source": None})
        output.append(row)

    rates_24 = [r for r in output if r["gold_24k_per_g"] is not None]
    rates_22 = [r for r in output if r["gold_22k_per_g"] is not None]
    coins = [r for r in output if r["coin_10g_total"] is not None]
    return {
        "city": city,
        "retailers": output,
        "summary": {
            "retailer_count": len(output),
            "quoted_count": sum(1 for r in output if r["quote_status"] != "not_entered"),
            "gold_24k_lowest": min(rates_24, key=lambda r: r["gold_24k_per_g"])["id"] if rates_24 else None,
            "gold_22k_lowest": min(rates_22, key=lambda r: r["gold_22k_per_g"])["id"] if rates_22 else None,
            "coin_10g_lowest": min(coins, key=lambda r: r["coin_10g_total"])["id"] if coins else None,
        },
        "comparison_notes": [
            "Retail base rates are not final invoice prices. Add 3% GST and the seller's making/coin premium where applicable.",
            "Compare like-for-like purity, fineness, net weight, city, quote time and tax basis.",
            "Automatic public-page rates are attempted for Kalyan, Tanishq, Malabar and Senco when current values can be parsed. Other retailers require a current official page or verified showroom quotation.",
            "Digital gold and physical minted products are separate categories; do not compare their price-only quotes without delivery, storage, spread and redemption terms.",
        ],
    }
