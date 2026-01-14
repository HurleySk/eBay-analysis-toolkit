from datetime import date, datetime


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
