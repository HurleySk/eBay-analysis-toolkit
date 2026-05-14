import pytest
from pathlib import Path
from ebay_tracker.scraper import parse_active_listing, extract_search_query, normalize_item_url


@pytest.fixture
def active_listing_html():
    fixture_path = Path(__file__).parent / "fixtures" / "ebay_active_listing.html"
    return fixture_path.read_text()


def test_parse_active_listing_title(active_listing_html):
    listing = parse_active_listing(active_listing_html, "123456789")
    assert listing.title == "Levi's 501 Original Fit Men's Jeans 32x30 Dark Wash"


def test_parse_active_listing_price(active_listing_html):
    listing = parse_active_listing(active_listing_html, "123456789")
    assert listing.price == 24.99


def test_parse_active_listing_shipping(active_listing_html):
    listing = parse_active_listing(active_listing_html, "123456789")
    assert listing.shipping == 5.99


def test_parse_active_listing_condition(active_listing_html):
    listing = parse_active_listing(active_listing_html, "123456789")
    assert listing.condition == "Pre-owned"


def test_parse_active_listing_seller(active_listing_html):
    listing = parse_active_listing(active_listing_html, "123456789")
    assert listing.seller == "jeans_outlet_99"


def test_parse_active_listing_item_specifics(active_listing_html):
    listing = parse_active_listing(active_listing_html, "123456789")
    assert listing.item_specifics["Brand"] == "Levi's"
    assert listing.item_specifics["Style"] == "501"
    assert listing.item_specifics["Waist Size"] == "32"
    assert listing.item_specifics["Inseam"] == "30"
    assert listing.item_specifics["Color"] == "Blue"


def test_parse_active_listing_item_id(active_listing_html):
    listing = parse_active_listing(active_listing_html, "123456789")
    assert listing.item_id == "123456789"


def test_extract_search_query_from_listing(active_listing_html):
    listing = parse_active_listing(active_listing_html, "123456789")
    suggested = extract_search_query(listing)
    assert "Levi's" in suggested.query or "levi" in suggested.query.lower()
    assert "501" in suggested.query
    assert suggested.raw_attributes["Brand"] == "Levi's"


def test_extract_search_query_filters(active_listing_html):
    listing = parse_active_listing(active_listing_html, "123456789")
    suggested = extract_search_query(listing)
    assert suggested.filters.get("condition") == "Pre-owned"


def test_normalize_item_url_full_url():
    url, item_id = normalize_item_url("https://www.ebay.com/itm/123456789")
    assert item_id == "123456789"
    assert "ebay.com/itm/123456789" in url


def test_normalize_item_url_with_query_params():
    url, item_id = normalize_item_url("https://www.ebay.com/itm/123456789?hash=item123&foo=bar")
    assert item_id == "123456789"


def test_normalize_item_url_item_id_only():
    url, item_id = normalize_item_url("123456789")
    assert item_id == "123456789"
    assert "ebay.com/itm/123456789" in url


def test_normalize_item_url_invalid():
    with pytest.raises(ValueError, match="Could not extract"):
        normalize_item_url("not-a-valid-input")
