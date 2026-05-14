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


def test_parse_active_listing_no_breadcrumb():
    from ebay_tracker.scraper import parse_active_listing
    html = """<html><body>
    <h1 class="x-item-title__mainTitle"><span>Test Item</span></h1>
    <div class="x-price-primary"><span class="ux-textspans">US $10.00</span></div>
    </body></html>"""
    listing = parse_active_listing(html, "999")
    assert listing.category_id is None
    assert listing.title == "Test Item"


# --- Query generation: Model-based improvements ---

from ebay_tracker.models import ActiveListing


def test_extract_search_query_uses_model_when_contains_brand():
    listing = ActiveListing(
        item_id="1", title="Rancourt Gilman Camp-moc Heritage Brown 9.5D",
        price=99.0, shipping=27.76, condition="Pre-owned", category_id=11450,
        item_specifics={
            "Brand": "Rancourt", "Style": "Camp Moc",
            "Model": "Rancourt Gilman Camp-moc",
        },
        url="", seller=None,
    )
    suggested = extract_search_query(listing)
    assert "Gilman" in suggested.query
    assert "Rancourt" in suggested.query


def test_extract_search_query_prepends_brand_when_model_lacks_it():
    listing = ActiveListing(
        item_id="2", title="Gilman Camp-moc 10D",
        price=99.0, shipping=0.0, condition="Pre-owned", category_id=11450,
        item_specifics={
            "Brand": "Rancourt", "Style": "Camp Moc",
            "Model": "Gilman Camp-moc",
        },
        url="", seller=None,
    )
    suggested = extract_search_query(listing)
    assert suggested.query == "Rancourt Gilman Camp-moc"


def test_extract_search_query_falls_back_to_style_without_model():
    listing = ActiveListing(
        item_id="3", title="Levi's 501 Jeans 32x30",
        price=25.0, shipping=5.99, condition="Pre-owned", category_id=11483,
        item_specifics={
            "Brand": "Levi's", "Style": "501",
            "Waist Size": "32", "Inseam": "30",
        },
        url="", seller=None,
    )
    suggested = extract_search_query(listing)
    assert "Levi's" in suggested.query
    assert "501" in suggested.query


def test_extract_search_query_no_generic_keyword_with_model():
    listing = ActiveListing(
        item_id="4", title="Rancourt Gilman Camp-moc Shoes Brown",
        price=99.0, shipping=0.0, condition="Pre-owned", category_id=11450,
        item_specifics={
            "Brand": "Rancourt", "Model": "Rancourt Gilman Camp-moc",
        },
        url="", seller=None,
    )
    suggested = extract_search_query(listing)
    assert "shoes" not in suggested.query.lower()


def test_extract_search_query_shoe_size_in_filters():
    listing = ActiveListing(
        item_id="5", title="Rancourt Gilman Camp-moc 9.5D",
        price=99.0, shipping=0.0, condition="Pre-owned", category_id=11450,
        item_specifics={
            "Brand": "Rancourt", "Model": "Rancourt Gilman Camp-moc",
            "US Shoe Size": "9.5",
        },
        url="", seller=None,
    )
    suggested = extract_search_query(listing)
    assert "9.5" not in suggested.query
    assert suggested.filters.get("shoe_size") == "9.5"


def test_extract_search_query_model_same_as_brand():
    listing = ActiveListing(
        item_id="6", title="Rancourt Shoes",
        price=99.0, shipping=0.0, condition="Pre-owned", category_id=11450,
        item_specifics={
            "Brand": "Rancourt", "Model": "Rancourt",
            "Style": "Camp Moc",
        },
        url="", seller=None,
    )
    suggested = extract_search_query(listing)
    assert "Camp Moc" in suggested.query


# --- build_search_url shoe size filter ---

from ebay_tracker.scraper import build_search_url


def test_build_search_url_includes_shoe_size_aspect():
    url = build_search_url("Rancourt Gilman", {"category": 11450, "shoe_size": "9.5"})
    assert "US+Shoe+Size=9.5" in url or "US%20Shoe%20Size=9.5" in url
    assert "rt=nc" in url
    assert "LH_SpecificOnly=1" in url
