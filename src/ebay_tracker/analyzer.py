from datetime import date

import pandas as pd
import numpy as np

from ebay_tracker.models import Listing


def analyze_listings(listings: list[Listing]) -> dict:
    """Analyze listings and return statistics."""
    if not listings:
        return {
            "count": 0,
            "price": {
                "min": None,
                "max": None,
                "median": None,
                "mean": None,
                "std_dev": None,
                "percentiles": {"p20": None, "p50": None, "p80": None},
            },
            "frequency": {
                "avg_days_between": None,
                "listings_per_month": None,
            },
            "trend": "unknown",
        }

    prices = [l.price for l in listings]
    df = pd.DataFrame({"price": prices})

    # Price statistics
    price_stats = {
        "min": float(df["price"].min()),
        "max": float(df["price"].max()),
        "median": float(df["price"].median()),
        "mean": float(df["price"].mean()),
        "std_dev": float(df["price"].std()) if len(prices) > 1 else 0.0,
        "percentiles": {
            "p20": float(df["price"].quantile(0.20)),
            "p50": float(df["price"].quantile(0.50)),
            "p80": float(df["price"].quantile(0.80)),
        },
    }

    # Frequency statistics
    frequency_stats = calculate_frequency(listings)

    # Trend analysis
    trend = calculate_trend(listings)

    return {
        "count": len(listings),
        "price": price_stats,
        "frequency": frequency_stats,
        "trend": trend,
    }


def calculate_frequency(listings: list[Listing]) -> dict:
    """Calculate listing frequency statistics."""
    if len(listings) < 2:
        return {
            "avg_days_between": None,
            "listings_per_month": None,
        }

    # Get listings with valid dates
    dated_listings = [l for l in listings if l.sold_date]
    if len(dated_listings) < 2:
        return {
            "avg_days_between": None,
            "listings_per_month": None,
        }

    # Sort by date
    dates = sorted([l.sold_date for l in dated_listings])

    # Calculate days between listings
    total_days = (dates[-1] - dates[0]).days
    num_listings = len(dates)

    if total_days == 0:
        return {
            "avg_days_between": 0.0,
            "listings_per_month": float("inf"),
        }

    avg_days = total_days / (num_listings - 1)
    listings_per_month = 30.0 / avg_days if avg_days > 0 else float("inf")

    return {
        "avg_days_between": round(avg_days, 1),
        "listings_per_month": round(listings_per_month, 1),
    }


def calculate_trend(listings: list[Listing]) -> str:
    """Determine price trend (rising, falling, or stable)."""
    if len(listings) < 3:
        return "stable"

    # Get listings with dates, sorted chronologically
    dated = [(l.sold_date, l.price) for l in listings if l.sold_date]
    if len(dated) < 3:
        return "stable"

    dated.sort(key=lambda x: x[0])

    # Simple linear regression to determine trend
    prices = [p for _, p in dated]
    x = np.arange(len(prices))

    # Calculate slope
    slope = np.polyfit(x, prices, 1)[0]
    mean_price = np.mean(prices)

    # Consider significant if slope > 5% of mean price per period
    threshold = mean_price * 0.05 / len(prices)

    if slope > threshold:
        return "rising"
    elif slope < -threshold:
        return "falling"
    return "stable"


def get_price_percentile(listings: list[Listing], target_price: float) -> float:
    """Get the percentile rank of a target price within the listings."""
    if not listings:
        return 0.0

    prices = sorted([l.price for l in listings])
    below = sum(1 for p in prices if p < target_price)
    return below / len(prices)


def predict_wait_time(
    target_price: float,
    percentile: float,
    avg_days_between: float,
) -> float:
    """Predict how many days to wait for a listing at target price."""
    if percentile <= 0:
        return float("inf")
    return round(avg_days_between / percentile, 1)


def get_recommendation(
    listings: list[Listing],
    target_price: float | None = None,
) -> dict:
    """Get a recommendation for buying."""
    stats = analyze_listings(listings)

    if stats["count"] == 0:
        return {
            "has_data": False,
            "message": "No data available. Run fetch to collect listings.",
        }

    p20 = stats["price"]["percentiles"]["p20"]
    avg_days = stats["frequency"]["avg_days_between"]

    result = {
        "has_data": True,
        "good_deal_threshold": p20,
        "median_price": stats["price"]["median"],
    }

    if target_price:
        percentile = get_price_percentile(listings, target_price)
        if avg_days and percentile > 0:
            wait_time = predict_wait_time(target_price, percentile, avg_days)
            result["target_price"] = target_price
            result["target_percentile"] = round(percentile * 100, 1)
            result["expected_wait_days"] = wait_time

    return result
