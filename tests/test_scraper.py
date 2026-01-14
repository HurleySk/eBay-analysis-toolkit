import pytest
from pathlib import Path
from datetime import date


@pytest.fixture
def sample_html():
    """Load sample eBay HTML fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "ebay_sold_listings.html"
    return fixture_path.read_text()


def test_parse_listings_extracts_all_items(sample_html):
    from ebay_tracker.scraper import parse_listings

    listings = parse_listings(sample_html, search_id=1)

    assert len(listings) == 3


def test_parse_listings_extracts_item_details(sample_html):
    from ebay_tracker.scraper import parse_listings

    listings = parse_listings(sample_html, search_id=1)

    # Check first listing
    first = listings[0]
    assert first.ebay_item_id == "123456789"
    assert first.title == "Levi's 501 Original Fit Jeans 32x30 Dark Wash"
    assert first.price == 45.00
    assert first.shipping == 5.99
    assert first.condition == "Pre-owned"
    assert first.sold_date == date(2025, 1, 10)
    assert "123456789" in first.url


def test_parse_listings_handles_free_shipping(sample_html):
    from ebay_tracker.scraper import parse_listings

    listings = parse_listings(sample_html, search_id=1)

    # Second listing has free shipping
    second = listings[1]
    assert second.price == 38.50
    assert second.shipping == 0.0


def test_build_search_url():
    from ebay_tracker.scraper import build_search_url

    url = build_search_url("Levi's 501 32x30")

    assert "ebay.com" in url
    assert "Levi" in url
    assert "LH_Complete=1" in url
    assert "LH_Sold=1" in url


def test_build_search_url_with_filters():
    from ebay_tracker.scraper import build_search_url

    url = build_search_url("Levi's 501", filters={"condition": "Pre-owned", "max_price": 50})

    assert "LH_ItemCondition=" in url or "LH_PrefLoc" in url or "udhi=" in url


def test_extract_item_id_from_url():
    from ebay_tracker.scraper import extract_item_id

    assert extract_item_id("https://www.ebay.com/itm/123456789?hash=item123") == "123456789"
    assert extract_item_id("https://www.ebay.com/itm/987654321") == "987654321"


def test_parse_price():
    from ebay_tracker.scraper import parse_price

    assert parse_price("$45.00") == 45.00
    assert parse_price("$1,234.56") == 1234.56
    assert parse_price("$38.50") == 38.50


def test_parse_shipping():
    from ebay_tracker.scraper import parse_shipping

    assert parse_shipping("+$5.99 shipping") == 5.99
    assert parse_shipping("Free shipping") == 0.0
    assert parse_shipping("+$12.00 shipping") == 12.00


def test_parse_sold_date():
    from ebay_tracker.scraper import parse_sold_date

    assert parse_sold_date("Sold  Jan 10, 2025") == date(2025, 1, 10)
    assert parse_sold_date("Sold  Dec 25, 2024") == date(2024, 12, 25)
