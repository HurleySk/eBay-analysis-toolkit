import json
from datetime import date

from mcp.server.fastmcp import FastMCP

from ebay_tracker.config import (
    FeeConfig, ThresholdConfig,
    get_config, get_prefs_path, get_user_prefs, save_user_prefs,
)
from ebay_tracker.evaluator import run_profit_analysis as _run_analysis
from ebay_tracker.models import ActiveListing, Listing
from ebay_tracker.scraper import (
    build_search_url, extract_search_query,
    fetch_active_listing, fetch_page, parse_listings,
)

mcp = FastMCP(
    "ebay-resale",
    instructions=(
        "eBay resale profit analysis. Use evaluate_listing first to inspect a listing, "
        "then run_profit_analysis with a confirmed comp query. "
        "Use configure_fees/configure_thresholds to set user preferences."
    ),
)


def _listing_to_dict(listing: ActiveListing) -> dict:
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
) -> dict:
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
    html = fetch_page(url, config.proxy_url)
    comps = parse_listings(html, search_id=0)

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
    }

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
def evaluate_listing(url_or_item_id: str) -> str:
    """Fetch an active eBay listing and generate a suggested comp search query.
    Returns listing details and suggested query for review before running full analysis.
    Input: eBay listing URL (e.g. https://www.ebay.com/itm/123456) or item number."""
    result = _do_evaluate_listing(url_or_item_id)
    return json.dumps(result, indent=2)


@mcp.tool()
def run_profit_analysis(
    listing_data: str,
    comp_query: str,
    comp_filters: str = "{}",
    fee_overrides: str = "{}",
    threshold_overrides: str = "{}",
) -> str:
    """Run full resale profit analysis. Call evaluate_listing first, then pass listing_data
    from its response with a confirmed comp_query.
    listing_data: JSON string of listing details from evaluate_listing.
    comp_query: Search query for comparable sold items.
    comp_filters: JSON string of optional filters (condition, category, etc.).
    fee_overrides: JSON string to override fee settings for this analysis.
    threshold_overrides: JSON string to override threshold settings for this analysis."""
    result = _do_run_profit_analysis(
        listing_data=json.loads(listing_data),
        comp_query=comp_query,
        comp_filters=json.loads(comp_filters) if comp_filters else None,
        fee_overrides=json.loads(fee_overrides) if fee_overrides else None,
        threshold_overrides=json.loads(threshold_overrides) if threshold_overrides else None,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def configure_fees(
    final_value_pct: float | None = None,
    payment_processing_pct: float | None = None,
    payment_processing_flat: float | None = None,
    shipping_cost: float | None = None,
    sales_tax_rate: float | None = None,
    state: str | None = None,
) -> str:
    """Get or set fee configuration. Pass parameters to update, or call with no args to read current config.
    Persists to ~/.config/ebay-tracker/config.json."""
    kwargs = {
        "final_value_pct": final_value_pct,
        "payment_processing_pct": payment_processing_pct,
        "payment_processing_flat": payment_processing_flat,
        "shipping_cost": shipping_cost,
        "sales_tax_rate": sales_tax_rate,
        "state": state,
    }
    result = _do_configure_fees(**{k: v for k, v in kwargs.items() if v is not None})
    return json.dumps(result, indent=2)


@mcp.tool()
def configure_thresholds(
    min_profit_pct: float | None = None,
    min_profit_dollar: float | None = None,
    mode: str | None = None,
) -> str:
    """Get or set profit threshold configuration. Mode is 'and' (both must pass) or 'or' (either passes).
    Persists to ~/.config/ebay-tracker/config.json."""
    kwargs = {
        "min_profit_pct": min_profit_pct,
        "min_profit_dollar": min_profit_dollar,
        "mode": mode,
    }
    result = _do_configure_thresholds(**{k: v for k, v in kwargs.items() if v is not None})
    return json.dumps(result, indent=2)


@mcp.tool()
def get_historical_stats(search_name: str) -> str:
    """Get price statistics and trends for an existing saved search.
    Queries the local database without making new eBay requests.
    search_name: Name of a search previously added via 'ebay-tracker add'."""
    result = _do_get_historical_stats(search_name)
    return json.dumps(result, indent=2)
