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
    with patch("ebay_tracker.server.fetch_active_listing", return_value=mock_active_listing):
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

    with patch("ebay_tracker.server.fetch_page") as mock_fetch, \
         patch("ebay_tracker.server.parse_listings") as mock_parse:
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
