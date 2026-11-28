from app.retailer_feeds import parse_malabar, parse_senco, parse_tanishq
from app.retailers import retailer_directory


def test_tanishq_parser_reads_published_22k_and_24k_rates():
    html = """
    <h2>22 Kt Gold Rate</h2>
    <table><tr><th>Grammage</th><th>Today</th><th>Yesterday</th></tr>
    <tr><td>1 G</td><td>₹ 11,490</td><td>₹ 11,350</td></tr>
    </table>
    <h2>24 Kt Gold Rate</h2>
    <table><tr><th>Grammage</th><th>Today</th><th>Yesterday</th></tr>
    <tr><td>1 G</td><td>₹ 12,540</td><td>₹ 12,400</td></tr>
    </table>
    """
    quote = parse_tanishq(html, "https://www.tanishq.co.in/gold-rate.html")
    assert quote["gold_22k_per_g"] == 11490
    assert quote["gold_24k_per_g"] == 12540
    assert quote["status"] == "automatic"


def test_malabar_parser_reads_rates_and_local_update_timestamp():
    html = """
    <div>11770.00 INR/gms 22k (916)</div>
    <div>12840.00 INR/gms 24k (999)</div>
    <div>Last updated: 2026-11-27,14:20:29</div>
    """
    quote = parse_malabar(html, "https://www.malabargoldanddiamonds.com/in/mh/en/live-gold-rate.html")
    assert quote["gold_22k_per_g"] == 11770
    assert quote["gold_24k_per_g"] == 12840
    assert quote["timestamp"].endswith("+05:30")


def test_senco_parser_reads_city_page_22k_and_24k_rates():
    html = """
    <div>₹14,548/Gram (22ct)</div>
    <p>The current 24K gold rate in Pune is ₹15,878 per gram.</p>
    """
    quote = parse_senco(html, "https://sencogoldanddiamonds.com/gold-rate-today/pune", "Pune")
    assert quote["gold_22k_per_g"] == 14548
    assert quote["gold_24k_per_g"] == 15878


def test_manual_retailer_quote_takes_precedence_over_automatic_feed():
    automatic = {
        "retailer_id": "tanishq",
        "gold_22k_per_g": 11490,
        "gold_24k_per_g": 12540,
        "coin_10g_total": None,
        "making_charge_pct": None,
        "source": "Tanishq public rate page",
        "source_url": "https://www.tanishq.co.in/gold-rate.html",
        "timestamp": "2026-11-28T00:00:00+05:30",
        "status": "automatic",
        "notes": "Public quote",
    }
    manual = {
        "retailer_id": "tanishq",
        "gold_22k_per_g": 11500,
        "gold_24k_per_g": None,
        "coin_10g_total": None,
        "making_charge_pct": None,
        "source": "Pune showroom quotation",
        "source_url": None,
        "timestamp": "2026-11-28T10:00:00+05:30",
        "status": "manual",
        "notes": "Verified at store",
    }
    result = retailer_directory("Pune", [manual], automatic_quotes={"tanishq": automatic})
    tanishq = next(row for row in result["retailers"] if row["id"] == "tanishq")
    assert tanishq["gold_22k_per_g"] == 11500
    assert tanishq["quote_status"] == "manual"
