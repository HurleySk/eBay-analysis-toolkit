import pytest
from datetime import date
from pathlib import Path
import tempfile


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        from ebay_tracker.db import Database
        db = Database(db_path)
        db.init()
        yield db
        db.close()


def test_database_init_creates_tables(temp_db):
    # Check tables exist by querying sqlite_master
    cursor = temp_db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]

    assert "searches" in tables
    assert "listings" in tables
    assert "fetch_log" in tables


def test_add_search(temp_db):
    from ebay_tracker.models import Search

    search = Search(
        id=None,
        name="Levi's 501 32x30",
        query="Levi's 501 32x30",
        filters={"condition": "Pre-owned"},
        created_at=None,
        last_fetched_at=None,
    )

    search_id = temp_db.add_search(search)

    assert search_id == 1

    # Verify it was saved
    saved = temp_db.get_search_by_name("Levi's 501 32x30")
    assert saved is not None
    assert saved.name == "Levi's 501 32x30"
    assert saved.filters == {"condition": "Pre-owned"}


def test_get_all_searches(temp_db):
    from ebay_tracker.models import Search

    temp_db.add_search(Search(None, "Search 1", "query1", None, None, None))
    temp_db.add_search(Search(None, "Search 2", "query2", None, None, None))

    searches = temp_db.get_all_searches()

    assert len(searches) == 2
    assert searches[0].name == "Search 1"
    assert searches[1].name == "Search 2"


def test_add_listing(temp_db):
    from ebay_tracker.models import Search, Listing

    # First add a search
    search_id = temp_db.add_search(
        Search(None, "Test Search", "test query", None, None, None)
    )

    listing = Listing(
        id=None,
        search_id=search_id,
        ebay_item_id="123456789",
        title="Test Item",
        price=45.00,
        shipping=5.99,
        condition="Pre-owned",
        sold_date=date(2025, 1, 10),
        url="https://www.ebay.com/itm/123456789",
        created_at=None,
    )

    listing_id = temp_db.add_listing(listing)

    assert listing_id == 1


def test_add_listing_ignores_duplicates(temp_db):
    from ebay_tracker.models import Search, Listing

    search_id = temp_db.add_search(
        Search(None, "Test Search", "test query", None, None, None)
    )

    listing = Listing(
        id=None,
        search_id=search_id,
        ebay_item_id="123456789",
        title="Test Item",
        price=45.00,
        shipping=5.99,
        condition="Pre-owned",
        sold_date=date(2025, 1, 10),
        url="https://www.ebay.com/itm/123456789",
        created_at=None,
    )

    # Add same listing twice
    temp_db.add_listing(listing)
    temp_db.add_listing(listing)  # Should not raise

    # Should only have one listing
    listings = temp_db.get_listings_for_search(search_id)
    assert len(listings) == 1


def test_get_listings_for_search(temp_db):
    from ebay_tracker.models import Search, Listing

    search_id = temp_db.add_search(
        Search(None, "Test Search", "test query", None, None, None)
    )

    for i in range(3):
        temp_db.add_listing(Listing(
            id=None,
            search_id=search_id,
            ebay_item_id=f"item{i}",
            title=f"Item {i}",
            price=40.00 + i * 5,
            shipping=None,
            condition="Pre-owned",
            sold_date=date(2025, 1, 10 + i),
            url=f"https://www.ebay.com/itm/item{i}",
            created_at=None,
        ))

    listings = temp_db.get_listings_for_search(search_id)

    assert len(listings) == 3


def test_delete_search_cascades_to_listings(temp_db):
    from ebay_tracker.models import Search, Listing

    search_id = temp_db.add_search(
        Search(None, "Test Search", "test query", None, None, None)
    )

    temp_db.add_listing(Listing(
        id=None,
        search_id=search_id,
        ebay_item_id="item1",
        title="Item 1",
        price=45.00,
        shipping=None,
        condition="Pre-owned",
        sold_date=date(2025, 1, 10),
        url="https://www.ebay.com/itm/item1",
        created_at=None,
    ))

    temp_db.delete_search(search_id)

    assert temp_db.get_search_by_name("Test Search") is None
    assert len(temp_db.get_listings_for_search(search_id)) == 0


def test_update_search(temp_db):
    from ebay_tracker.models import Search

    search = Search(None, "Test Search", "original query", {"color": "Blue"}, None, None)
    search_id = temp_db.add_search(search)

    # Update query
    temp_db.update_search(search_id, query="new query")
    updated = temp_db.get_search_by_id(search_id)
    assert updated.query == "new query"
    assert updated.filters == {"color": "Blue"}  # Filters unchanged

    # Update filters
    temp_db.update_search(search_id, filters={"color": "Black", "size": "32"})
    updated = temp_db.get_search_by_id(search_id)
    assert updated.query == "new query"  # Query unchanged
    assert updated.filters == {"color": "Black", "size": "32"}

    # Clear filters
    temp_db.update_search(search_id, filters={})
    updated = temp_db.get_search_by_id(search_id)
    assert updated.filters is None or updated.filters == {}
