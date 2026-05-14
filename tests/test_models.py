from datetime import date, datetime

from ebay_tracker.models import (
    ActiveListing, SuggestedQuery, NetProceeds,
    SellTimePrediction, ProfitAnalysis, Listing,
)


def test_search_model_creation():
    from ebay_tracker.models import Search

    search = Search(
        id=1,
        name="Levi's 501 32x30",
        query="Levi's 501 32x30",
        filters={"condition": "Pre-owned"},
        created_at=datetime(2025, 1, 14, 12, 0, 0),
        last_fetched_at=None,
    )

    assert search.name == "Levi's 501 32x30"
    assert search.filters == {"condition": "Pre-owned"}


def test_listing_model_creation():
    from ebay_tracker.models import Listing

    listing = Listing(
        id=1,
        search_id=1,
        ebay_item_id="123456789",
        title="Levi's 501 Original Fit Jeans 32x30 Dark Wash",
        price=45.00,
        shipping=5.99,
        condition="Pre-owned",
        sold_date=date(2025, 1, 10),
        url="https://www.ebay.com/itm/123456789",
        created_at=datetime(2025, 1, 14, 12, 0, 0),
    )

    assert listing.price == 45.00
    assert listing.total_price == 50.99


def test_listing_total_price_with_none_shipping():
    from ebay_tracker.models import Listing

    listing = Listing(
        id=1,
        search_id=1,
        ebay_item_id="123456789",
        title="Test Item",
        price=45.00,
        shipping=None,
        condition="Pre-owned",
        sold_date=date(2025, 1, 10),
        url="https://www.ebay.com/itm/123456789",
        created_at=datetime(2025, 1, 14, 12, 0, 0),
    )

    assert listing.total_price == 45.00


def test_active_listing_creation():
    listing = ActiveListing(
        item_id="123456",
        title="Levi's 501 Jeans 32x30",
        price=25.00,
        shipping=5.99,
        condition="Pre-owned",
        category_id=11483,
        item_specifics={"Brand": "Levi's", "Size": "32x30"},
        url="https://www.ebay.com/itm/123456",
        seller="seller123",
    )
    assert listing.item_id == "123456"
    assert listing.price == 25.00
    assert listing.item_specifics["Brand"] == "Levi's"


def test_active_listing_total_cost():
    import pytest
    listing = ActiveListing(
        item_id="123456", title="Test", price=25.00, shipping=5.99,
        condition=None, category_id=None, item_specifics={},
        url="https://www.ebay.com/itm/123456", seller=None,
    )
    assert listing.total_cost == pytest.approx(30.99)


def test_active_listing_total_cost_no_shipping():
    listing = ActiveListing(
        item_id="123456", title="Test", price=25.00, shipping=None,
        condition=None, category_id=None, item_specifics={},
        url="https://www.ebay.com/itm/123456", seller=None,
    )
    assert listing.total_cost == 25.00


def test_suggested_query_creation():
    sq = SuggestedQuery(
        query="Levi's 501 jeans 32x30",
        filters={"condition": "Pre-owned", "category": 11483},
        raw_attributes={"Brand": "Levi's", "Size": "32x30"},
    )
    assert sq.query == "Levi's 501 jeans 32x30"
    assert sq.filters["category"] == 11483


def test_net_proceeds_creation():
    np_result = NetProceeds(
        gross=50.00, final_value_fee=6.625, payment_processing_fee=1.475,
        shipping_cost=0.00, total_fees=8.10, net=41.90,
    )
    assert np_result.net == 41.90
    assert np_result.total_fees == 8.10


def test_sell_time_prediction_creation():
    pred = SellTimePrediction(
        median_days=7.5, fast_days=3.2, slow_days=14.1,
        ninety_pct_days=21.0, confidence="high", sample_size=25,
        price_tier="below_median",
    )
    assert pred.median_days == 7.5
    assert pred.confidence == "high"


def test_profit_analysis_creation():
    comps = [
        Listing(1, 1, "c1", "Comp 1", 45.0, 0.0, "Pre-owned", date(2025, 1, 5), None, None),
    ]
    analysis = ProfitAnalysis(
        purchase_price=25.00, purchase_shipping=5.99, purchase_tax=2.17,
        total_purchase_cost=33.16, expected_sale_price=45.00,
        sale_price_25th=38.00, sale_price_75th=52.00,
        net_proceeds=NetProceeds(
            gross=45.00, final_value_fee=5.96, payment_processing_fee=1.36,
            shipping_cost=0.00, total_fees=7.32, net=37.68,
        ),
        projected_profit=4.52, projected_profit_pct=13.63,
        meets_threshold=False,
        threshold_detail="13.6% >= 20% AND $4.52 >= $10.00: FAIL (both required)",
        time_to_sell=None, confidence="low", comp_count=1, comps=comps,
    )
    assert analysis.projected_profit == 4.52
    assert analysis.meets_threshold is False
