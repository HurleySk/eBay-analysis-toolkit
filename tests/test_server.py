import pytest
from unittest.mock import patch
from datetime import date

from ebay_tracker.server import (
    _do_evaluate_listing,
    _do_run_profit_analysis,
    _do_configure_fees,
    _do_configure_thresholds,
    _do_test_connection,
)
from ebay_tracker.models import ActiveListing, Listing


@pytest.fixture
def mock_active_listing():
    return ActiveListing(
        item_id="123456",
        title="Levi's 501 Jeans 32x30",
        price=25.00,
        shipping=5.99,
        condition="Pre-owned",
        category_id=11483,
        item_specifics={"Brand": "Levi's", "Style": "501"},
        url="https://www.ebay.com/itm/123456",
        seller="seller1",
    )


def test_do_evaluate_listing(mock_active_listing):
    with patch("ebay_tracker.scraper.fetch_active_listing", return_value=mock_active_listing):
        result = _do_evaluate_listing("123456")
    assert result["listing"]["item_id"] == "123456"
    assert result["listing"]["price"] == 25.00
    assert "suggested_query" in result
    assert result["suggested_query"]["query"] != ""


def test_do_run_profit_analysis():
    comps_data = [
        {"price": 45.0, "shipping": 0.0, "condition": "Pre-owned",
         "sold_date": "2025-01-05", "title": "Comp 1", "ebay_item_id": "c1"},
        {"price": 50.0, "shipping": 0.0, "condition": "Pre-owned",
         "sold_date": "2025-01-10", "title": "Comp 2", "ebay_item_id": "c2"},
        {"price": 48.0, "shipping": 0.0, "condition": "Pre-owned",
         "sold_date": "2025-01-15", "title": "Comp 3", "ebay_item_id": "c3"},
    ]
    listing_data = {
        "item_id": "123456",
        "title": "Levi's 501 Jeans 32x30",
        "price": 25.00,
        "shipping": 5.99,
        "condition": "Pre-owned",
        "category_id": 11483,
        "item_specifics": {},
        "url": "https://www.ebay.com/itm/123456",
        "seller": "seller1",
    }

    with patch("ebay_tracker.scraper.fetch_page") as mock_fetch, \
         patch("ebay_tracker.scraper.parse_listings") as mock_parse:
        mock_fetch.return_value = "<html></html>"
        mock_parse.return_value = [
            Listing(None, 0, c["ebay_item_id"], c["title"], c["price"], c["shipping"],
                    c["condition"], date.fromisoformat(c["sold_date"]), None, None)
            for c in comps_data
        ]
        result = _do_run_profit_analysis(
            listing_data=listing_data,
            comp_query="Levi's 501 jeans 32x30",
            comp_filters={},
        )

    assert "projected_profit" in result
    assert "meets_threshold" in result
    assert "verdict" in result
    assert result["comp_count"] == 3
    assert "comp_sample" in result
    assert len(result["comp_sample"]) <= 10
    assert "comps_before_filter" in result
    assert "comps_after_filter" in result


def test_do_configure_fees(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr("ebay_tracker.config.get_prefs_path", lambda: config_path)
    monkeypatch.setattr("ebay_tracker.config.get_prefs_path", lambda: config_path)

    result = _do_configure_fees(shipping_cost=8.50, sales_tax_rate=7.0, state="TX")
    assert result["fees"]["shipping_cost"] == 8.50
    assert result["fees"]["sales_tax_rate"] == 7.0
    assert result["fees"]["state"] == "TX"


def test_do_configure_thresholds(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr("ebay_tracker.config.get_prefs_path", lambda: config_path)
    monkeypatch.setattr("ebay_tracker.config.get_prefs_path", lambda: config_path)

    result = _do_configure_thresholds(min_profit_pct=25.0, mode="or")
    assert result["thresholds"]["min_profit_pct"] == 25.0
    assert result["thresholds"]["mode"] == "or"


def test_do_test_connection_no_proxy(monkeypatch):
    monkeypatch.delenv("DECODO_PROXY_URL", raising=False)
    result = _do_test_connection()
    assert result["proxy_configured"] is False
    assert "error" in result


# --- Comp filtering ---

from ebay_tracker.server import _filter_comps_by_brand, _remove_price_outliers


def _make_comp(title, price):
    return Listing(
        id=None, search_id=0, ebay_item_id="x",
        title=title, price=price, shipping=0.0,
        condition="Pre-owned", sold_date=date(2025, 1, 10),
        url=None, created_at=None,
    )


def test_filter_comps_by_brand_keeps_matches():
    comps = [
        _make_comp("Rancourt Gilman Camp Moc Brown", 110.0),
        _make_comp("Quoddy Blucher rancourt yuketen", 45.0),
        _make_comp("LL Bean Camp Moc Leather", 30.0),
        _make_comp("Rancourt & Co Ranger Moc", 150.0),
    ]
    filtered = _filter_comps_by_brand(comps, "Rancourt")
    assert len(filtered) == 3


def test_filter_comps_by_brand_case_insensitive():
    comps = [_make_comp("RANCOURT shoes", 100.0)]
    filtered = _filter_comps_by_brand(comps, "rancourt")
    assert len(filtered) == 1


def test_filter_comps_by_brand_empty_string_skips():
    comps = [_make_comp("Anything", 50.0)]
    filtered = _filter_comps_by_brand(comps, "")
    assert len(filtered) == 1


def test_remove_price_outliers_drops_extremes():
    comps = [
        _make_comp("A", 100.0),
        _make_comp("B", 110.0),
        _make_comp("C", 105.0),
        _make_comp("D", 95.0),
        _make_comp("E", 900.0),
        _make_comp("F", 2.0),
        _make_comp("G", 102.0),
        _make_comp("H", 98.0),
    ]
    filtered = _remove_price_outliers(comps)
    prices = [c.price for c in filtered]
    assert 900.0 not in prices
    assert 2.0 not in prices
    assert len(filtered) == 6


def test_remove_price_outliers_keeps_all_when_tight():
    comps = [_make_comp("A", p) for p in [100, 105, 110, 95, 108, 103, 107, 99]]
    filtered = _remove_price_outliers(comps)
    assert len(filtered) == 8


def test_remove_price_outliers_needs_minimum_comps():
    comps = [_make_comp("A", 100.0), _make_comp("B", 900.0)]
    filtered = _remove_price_outliers(comps)
    assert len(filtered) == 2


def test_remove_price_outliers_skips_small_sets():
    """With fewer than 8 comps, don't remove outliers."""
    comps = [_make_comp("A", p) for p in [10, 100, 105, 110, 900]]
    filtered = _remove_price_outliers(comps)
    assert len(filtered) == 5


def test_do_run_profit_analysis_with_brand_filter():
    comps_data = [
        {"title": "Rancourt Gilman Camp Moc Brown", "price": 110.0,
         "ebay_item_id": "c1", "shipping": 0.0, "condition": "Pre-owned", "sold_date": "2025-01-05"},
        {"title": "Quoddy Blucher Moc", "price": 45.0,
         "ebay_item_id": "c2", "shipping": 0.0, "condition": "Pre-owned", "sold_date": "2025-01-10"},
        {"title": "Rancourt Ranger Moc Natural", "price": 150.0,
         "ebay_item_id": "c3", "shipping": 0.0, "condition": "Pre-owned", "sold_date": "2025-01-15"},
    ]
    listing_data = {
        "item_id": "999",
        "title": "Rancourt Gilman Camp-moc",
        "price": 99.0,
        "shipping": 27.76,
        "item_specifics": {"Brand": "Rancourt"},
        "url": "",
        "seller": "test",
    }

    with patch("ebay_tracker.scraper.fetch_page") as mock_fetch, \
         patch("ebay_tracker.scraper.parse_listings") as mock_parse:
        mock_fetch.return_value = "<html></html>"
        mock_parse.return_value = [
            Listing(None, 0, c["ebay_item_id"], c["title"], c["price"], c["shipping"],
                    c["condition"], date.fromisoformat(c["sold_date"]), None, None)
            for c in comps_data
        ]
        result = _do_run_profit_analysis(
            listing_data=listing_data,
            comp_query="Rancourt Camp Moc",
            filter_brand="Rancourt",
        )

    assert result["comps_before_filter"] == 3
    assert result["comps_after_filter"] == 2
    assert result["comp_count"] == 2
