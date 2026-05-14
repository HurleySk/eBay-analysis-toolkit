import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

from mcp.server.fastmcp import FastMCP

# Single-threaded executor: Playwright's sync API binds its event loop to the
# creating thread, so all browser operations must run on the same thread.
_playwright_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playwright")

mcp = FastMCP(
    "ebay-resale",
    instructions=(
        "eBay resale profit analysis. Use evaluate_listing first to inspect a listing, "
        "then run_profit_analysis with a confirmed comp query. "
        "Use configure_fees/configure_thresholds to set user preferences."
    ),
)


def _filter_comps_by_brand(comps: list, brand: str) -> list:
    if not brand:
        return comps
    brand_lower = brand.lower()
    return [c for c in comps if brand_lower in c.title.lower()]


def _remove_price_outliers(comps: list) -> list:
    if len(comps) < 8:
        return comps
    prices = sorted(c.price for c in comps)
    q1 = prices[len(prices) // 4]
    q3 = prices[3 * len(prices) // 4]
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return [c for c in comps if lower <= c.price <= upper]


def _listing_to_dict(listing) -> dict:
    return {
        "item_id": listing.item_id,
        "title": listing.title,
        "price": listing.price,
        "shipping": listing.shipping,
        "condition": listing.condition,
        "category_id": listing.category_id,
        "item_specifics": listing.item_specifics,
        "url": listing.url,
        "seller": listing.seller,
    }


def _do_evaluate_listing(url_or_item_id: str) -> dict:
    from ebay_tracker.config import get_config
    from ebay_tracker.scraper import extract_search_query, fetch_active_listing

    config = get_config()
    listing = fetch_active_listing(url_or_item_id, config.proxy_url)
    suggested = extract_search_query(listing)
    return {
        "listing": _listing_to_dict(listing),
        "suggested_query": {
            "query": suggested.query,
            "filters": suggested.filters,
            "raw_attributes": suggested.raw_attributes,
        },
    }


def _do_run_profit_analysis(
    listing_data: dict,
    comp_query: str,
    comp_filters: dict | None = None,
    fee_overrides: dict | None = None,
    threshold_overrides: dict | None = None,
    filter_brand: str = "",
) -> dict:
    from ebay_tracker.config import FeeConfig, ThresholdConfig, get_config, get_user_prefs
    from ebay_tracker.evaluator import run_profit_analysis as _run_analysis
    from ebay_tracker.models import ActiveListing
    from ebay_tracker.scraper import build_search_url, fetch_page, parse_listings

    config = get_config()
    prefs = get_user_prefs()

    listing = ActiveListing(
        item_id=listing_data["item_id"],
        title=listing_data["title"],
        price=listing_data["price"],
        shipping=listing_data.get("shipping"),
        condition=listing_data.get("condition"),
        category_id=listing_data.get("category_id"),
        item_specifics=listing_data.get("item_specifics", {}),
        url=listing_data.get("url", ""),
        seller=listing_data.get("seller"),
    )

    fee_cfg = FeeConfig(
        final_value_pct=(fee_overrides or {}).get("final_value_pct", prefs.fees.final_value_pct),
        payment_processing_pct=(fee_overrides or {}).get("payment_processing_pct", prefs.fees.payment_processing_pct),
        payment_processing_flat=(fee_overrides or {}).get("payment_processing_flat", prefs.fees.payment_processing_flat),
        shipping_cost=(fee_overrides or {}).get("shipping_cost", prefs.fees.shipping_cost),
        sales_tax_rate=(fee_overrides or {}).get("sales_tax_rate", prefs.fees.sales_tax_rate),
    )
    threshold_cfg = ThresholdConfig(
        min_profit_pct=(threshold_overrides or {}).get("min_profit_pct", prefs.thresholds.min_profit_pct),
        min_profit_dollar=(threshold_overrides or {}).get("min_profit_dollar", prefs.thresholds.min_profit_dollar),
        mode=(threshold_overrides or {}).get("mode", prefs.thresholds.mode),
    )

    url = build_search_url(comp_query, comp_filters)
    html = fetch_page(url, config.proxy_url, use_browser=True)
    all_comps = parse_listings(html, search_id=0)
    comps_before_filter = len(all_comps)

    comps = list(all_comps)
    if filter_brand:
        comps = _filter_comps_by_brand(comps, filter_brand)
    n_before_iqr = len(comps)
    comps = _remove_price_outliers(comps)
    comps_after_filter = len(comps)
    outliers_removed = n_before_iqr - comps_after_filter

    quality_warning = None
    if not comps and comps_before_filter > 0:
        comps = all_comps
        comps_after_filter = len(comps)
        quality_warning = "All comps removed by filters, showing unfiltered results"
    elif outliers_removed > 0:
        quality_warning = f"Removed {outliers_removed} price outliers (IQR filter)"

    brand_from_listing = listing_data.get("item_specifics", {}).get("Brand", "")
    brand_match_rate = None
    if brand_from_listing and all_comps:
        brand_matches = sum(1 for c in all_comps if brand_from_listing.lower() in c.title.lower())
        brand_match_rate = round(brand_matches / len(all_comps) * 100, 1)

    if brand_match_rate is not None and brand_match_rate < 50 and not filter_brand and quality_warning is None:
        quality_warning = f"Only {brand_match_rate}% of comps match brand '{brand_from_listing}'"

    result = _run_analysis(listing, comps, fee_cfg, threshold_cfg)

    output = {
        "purchase_cost": result.total_purchase_cost,
        "expected_sale_price": result.expected_sale_price,
        "sale_price_25th": result.sale_price_25th,
        "sale_price_75th": result.sale_price_75th,
        "net_proceeds": result.net_proceeds.net,
        "fees": {
            "final_value_fee": result.net_proceeds.final_value_fee,
            "payment_processing_fee": result.net_proceeds.payment_processing_fee,
            "shipping_cost": result.net_proceeds.shipping_cost,
            "total_fees": result.net_proceeds.total_fees,
        },
        "projected_profit": result.projected_profit,
        "projected_profit_pct": result.projected_profit_pct,
        "meets_threshold": result.meets_threshold,
        "threshold_detail": result.threshold_detail,
        "verdict": "BUY" if result.meets_threshold else "PASS",
        "confidence": result.confidence,
        "comp_count": result.comp_count,
        "comp_sample": [
            {"title": c.title, "price": c.price}
            for c in comps[:10]
        ],
        "comps_before_filter": comps_before_filter,
        "comps_after_filter": comps_after_filter,
    }

    if brand_match_rate is not None:
        output["brand_match_rate"] = brand_match_rate
    if quality_warning:
        output["comp_quality_warning"] = quality_warning

    if result.time_to_sell:
        output["time_to_sell"] = {
            "median_days": result.time_to_sell.median_days,
            "fast_days": result.time_to_sell.fast_days,
            "slow_days": result.time_to_sell.slow_days,
            "ninety_pct_days": result.time_to_sell.ninety_pct_days,
            "confidence": result.time_to_sell.confidence,
            "price_tier": result.time_to_sell.price_tier,
        }

    return output


def _do_configure_fees(**kwargs) -> dict:
    from ebay_tracker.config import get_user_prefs, save_user_prefs

    prefs = get_user_prefs()
    for key, value in kwargs.items():
        if value is not None and hasattr(prefs.fees, key):
            setattr(prefs.fees, key, value)
    save_user_prefs(prefs)
    return {
        "fees": {
            "final_value_pct": prefs.fees.final_value_pct,
            "payment_processing_pct": prefs.fees.payment_processing_pct,
            "payment_processing_flat": prefs.fees.payment_processing_flat,
            "shipping_cost": prefs.fees.shipping_cost,
            "sales_tax_rate": prefs.fees.sales_tax_rate,
            "state": prefs.fees.state,
        }
    }


def _do_configure_thresholds(**kwargs) -> dict:
    from ebay_tracker.config import get_user_prefs, save_user_prefs

    prefs = get_user_prefs()
    for key, value in kwargs.items():
        if value is not None and hasattr(prefs.thresholds, key):
            setattr(prefs.thresholds, key, value)
    save_user_prefs(prefs)
    return {
        "thresholds": {
            "min_profit_pct": prefs.thresholds.min_profit_pct,
            "min_profit_dollar": prefs.thresholds.min_profit_dollar,
            "mode": prefs.thresholds.mode,
        }
    }


def _do_get_historical_stats(search_name: str) -> dict:
    from ebay_tracker.analyzer import analyze_listings
    from ebay_tracker.config import get_config
    from ebay_tracker.db import Database

    config = get_config()
    db = Database(config.db_path)
    db.init()

    search = db.get_search_by_name(search_name)
    if not search:
        db.close()
        return {"error": f"Search '{search_name}' not found"}

    listings = db.get_listings_for_search(search.id)
    db.close()

    if not listings:
        return {"search": search_name, "count": 0, "message": "No data. Run fetch first."}

    stats = analyze_listings(listings)
    return {"search": search_name, **stats}


@mcp.tool()
async def evaluate_listing(url_or_item_id: str) -> str:
    """Fetch an active eBay listing and generate a suggested comp search query.
    Returns listing details and suggested query for review before running full analysis.
    Input: eBay listing URL (e.g. https://www.ebay.com/itm/123456) or item number."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(_playwright_executor, _do_evaluate_listing, url_or_item_id)
    return json.dumps(result, indent=2)


@mcp.tool()
async def run_profit_analysis(
    listing_data: str,
    comp_query: str,
    comp_filters: str = "{}",
    fee_overrides: str = "{}",
    threshold_overrides: str = "{}",
    filter_brand: str = "",
) -> str:
    """Run full resale profit analysis. Call evaluate_listing first, then pass listing_data
    from its response with a confirmed comp_query.
    listing_data: JSON string of listing details from evaluate_listing.
    comp_query: Search query for comparable sold items.
    comp_filters: JSON string of optional filters (condition, category, etc.).
    fee_overrides: JSON string to override fee settings for this analysis.
    threshold_overrides: JSON string to override threshold settings for this analysis.
    filter_brand: Brand name to filter comps by (case-insensitive title match)."""
    parsed_listing = json.loads(listing_data)
    parsed_filters = json.loads(comp_filters) if comp_filters else None
    parsed_fees = json.loads(fee_overrides) if fee_overrides else None
    parsed_thresholds = json.loads(threshold_overrides) if threshold_overrides else None
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        _playwright_executor,
        lambda: _do_run_profit_analysis(
            listing_data=parsed_listing,
            comp_query=comp_query,
            comp_filters=parsed_filters,
            fee_overrides=parsed_fees,
            threshold_overrides=parsed_thresholds,
            filter_brand=filter_brand,
        ),
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def configure_fees(
    final_value_pct: float | None = None,
    payment_processing_pct: float | None = None,
    payment_processing_flat: float | None = None,
    shipping_cost: float | None = None,
    sales_tax_rate: float | None = None,
    state: str | None = None,
) -> str:
    """Get or set fee configuration. Pass parameters to update, or call with no args to read current config.
    Persists to ~/.config/ebay-tracker/config.json."""
    kwargs = {k: v for k, v in {
        "final_value_pct": final_value_pct,
        "payment_processing_pct": payment_processing_pct,
        "payment_processing_flat": payment_processing_flat,
        "shipping_cost": shipping_cost,
        "sales_tax_rate": sales_tax_rate,
        "state": state,
    }.items() if v is not None}
    result = await asyncio.to_thread(_do_configure_fees, **kwargs)
    return json.dumps(result, indent=2)


@mcp.tool()
async def configure_thresholds(
    min_profit_pct: float | None = None,
    min_profit_dollar: float | None = None,
    mode: str | None = None,
) -> str:
    """Get or set profit threshold configuration. Mode is 'and' (both must pass) or 'or' (either passes).
    Persists to ~/.config/ebay-tracker/config.json."""
    kwargs = {k: v for k, v in {
        "min_profit_pct": min_profit_pct,
        "min_profit_dollar": min_profit_dollar,
        "mode": mode,
    }.items() if v is not None}
    result = await asyncio.to_thread(_do_configure_thresholds, **kwargs)
    return json.dumps(result, indent=2)


def _do_test_connection() -> dict:
    from ebay_tracker.config import get_config
    from ebay_tracker.scraper import _get_browser_fetcher

    config = get_config()
    result = {
        "proxy_configured": config.proxy_url is not None,
        "proxy_ip": None,
        "browser_status": "unknown",
        "ebay_reachable": False,
    }

    if not config.proxy_url:
        result["error"] = "No proxy configured. Set DECODO_PROXY_URL in .env"
        return result

    try:
        from curl_cffi import requests as cffi_requests
        ip_resp = cffi_requests.get(
            "https://ip.decodo.com/json",
            proxy=config.proxy_url,
            impersonate="chrome",
            timeout=15,
        )
        if ip_resp.status_code == 200:
            ip_data = ip_resp.json()
            result["proxy_ip"] = ip_data.get("proxy", {}).get("ip", "unknown")
    except Exception as e:
        result["proxy_ip"] = f"error: {e}"

    try:
        fetcher = _get_browser_fetcher(config.proxy_url)
        result["browser_status"] = "running" if fetcher.is_running else "stopped (will start on demand)"
        html = fetcher.fetch("https://www.ebay.com/")
        result["ebay_reachable"] = len(html) > 1000
    except Exception as e:
        result["browser_status"] = f"error: {e}"

    return result


@mcp.tool()
async def test_connection() -> str:
    """Test proxy connectivity and browser health. Call this first if scraping fails.
    Returns proxy IP, browser status, and eBay reachability."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(_playwright_executor, _do_test_connection)
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_historical_stats(search_name: str) -> str:
    """Get price statistics and trends for an existing saved search.
    Queries the local database without making new eBay requests.
    search_name: Name of a search previously added via 'ebay-tracker add'."""
    result = await asyncio.to_thread(_do_get_historical_stats, search_name)
    return json.dumps(result, indent=2)
