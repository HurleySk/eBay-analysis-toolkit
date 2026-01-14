import pytest
from datetime import date

from ebay_tracker.models import Listing


@pytest.fixture
def sample_listings():
    """Create sample listings for testing."""
    return [
        Listing(1, 1, "item1", "Item 1", 30.00, 5.00, "Pre-owned", date(2025, 1, 1), None, None),
        Listing(2, 1, "item2", "Item 2", 40.00, 0.00, "Pre-owned", date(2025, 1, 5), None, None),
        Listing(3, 1, "item3", "Item 3", 35.00, 5.00, "Pre-owned", date(2025, 1, 10), None, None),
        Listing(4, 1, "item4", "Item 4", 50.00, 0.00, "New", date(2025, 1, 15), None, None),
        Listing(5, 1, "item5", "Item 5", 45.00, 5.00, "Pre-owned", date(2025, 1, 20), None, None),
    ]


def test_analyze_returns_stats_dict(sample_listings):
    from ebay_tracker.analyzer import analyze_listings

    stats = analyze_listings(sample_listings)

    assert "count" in stats
    assert "price" in stats
    assert "frequency" in stats
    assert "trend" in stats


def test_analyze_count(sample_listings):
    from ebay_tracker.analyzer import analyze_listings

    stats = analyze_listings(sample_listings)

    assert stats["count"] == 5


def test_analyze_price_stats(sample_listings):
    from ebay_tracker.analyzer import analyze_listings

    stats = analyze_listings(sample_listings)

    # Prices are 30, 40, 35, 50, 45 = sorted: 30, 35, 40, 45, 50
    assert stats["price"]["min"] == 30.00
    assert stats["price"]["max"] == 50.00
    assert stats["price"]["median"] == 40.00
    assert stats["price"]["mean"] == 40.00  # (30+40+35+50+45)/5 = 200/5 = 40


def test_analyze_price_percentiles(sample_listings):
    from ebay_tracker.analyzer import analyze_listings

    stats = analyze_listings(sample_listings)

    assert "percentiles" in stats["price"]
    assert "p20" in stats["price"]["percentiles"]
    assert "p50" in stats["price"]["percentiles"]
    assert "p80" in stats["price"]["percentiles"]


def test_analyze_frequency(sample_listings):
    from ebay_tracker.analyzer import analyze_listings

    stats = analyze_listings(sample_listings)

    # 5 listings over 19 days (Jan 1 to Jan 20) = ~4.75 days between listings
    assert "avg_days_between" in stats["frequency"]
    assert "listings_per_month" in stats["frequency"]
    assert stats["frequency"]["avg_days_between"] > 0


def test_analyze_trend_stable(sample_listings):
    from ebay_tracker.analyzer import analyze_listings

    stats = analyze_listings(sample_listings)

    # Prices: 30, 40, 35, 50, 45 - no clear trend
    assert stats["trend"] in ("stable", "rising", "falling")


def test_predict_wait_time():
    from ebay_tracker.analyzer import predict_wait_time

    # If avg 8 days between listings and target is 20th percentile
    # Expected wait = 8 / 0.20 = 40 days
    wait = predict_wait_time(
        target_price=32.00,
        percentile=0.20,
        avg_days_between=8.0,
    )

    assert wait == 40.0


def test_predict_wait_time_median():
    from ebay_tracker.analyzer import predict_wait_time

    # At median (50th percentile), wait = avg_days * 2
    wait = predict_wait_time(
        target_price=40.00,
        percentile=0.50,
        avg_days_between=8.0,
    )

    assert wait == 16.0


def test_get_price_percentile(sample_listings):
    from ebay_tracker.analyzer import get_price_percentile

    # Prices: 30, 35, 40, 45, 50
    percentile = get_price_percentile(sample_listings, 35.00)

    # 35 is at 25th percentile (1 value below, 4 total = 25%)
    assert 0.2 <= percentile <= 0.4


def test_analyze_empty_listings():
    from ebay_tracker.analyzer import analyze_listings

    stats = analyze_listings([])

    assert stats["count"] == 0
    assert stats["price"]["median"] is None
    assert stats["frequency"]["avg_days_between"] is None


def test_analyze_single_listing():
    from ebay_tracker.analyzer import analyze_listings

    listings = [
        Listing(1, 1, "item1", "Item 1", 50.00, 5.00, "Pre-owned", date(2025, 1, 10), None, None),
    ]

    stats = analyze_listings(listings)

    assert stats["count"] == 1
    assert stats["price"]["median"] == 50.00
    assert stats["price"]["min"] == 50.00
    assert stats["price"]["max"] == 50.00
