# eBay Tracker Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a CLI tool that scrapes eBay sold listings and provides price/availability predictions.

**Architecture:** Three-layer design: CLI (typer) → Services (scraper, analyzer, db) → Infrastructure (proxy, config). All requests through Decodo proxy. SQLite storage with raw SQL. TDD throughout.

**Tech Stack:** Python 3.11+, uv, typer, httpx, beautifulsoup4, pandas, rich, SQLite

---

## Task 1: Project Setup

**Files:**
- Create: `pyproject.toml`
- Create: `src/ebay_tracker/__init__.py`
- Create: `.env.example`
- Create: `.gitignore`

**Step 1: Initialize uv project**

Run:
```bash
cd /Users/skh/source/eBay-analysis-toolkit
uv init --name ebay-tracker --package
```

Expected: Creates `pyproject.toml` and `src/ebay_tracker/__init__.py`

**Step 2: Update pyproject.toml with dependencies**

Replace contents of `pyproject.toml`:

```toml
[project]
name = "ebay-tracker"
version = "0.1.0"
description = "CLI tool to track eBay sold listings and predict prices"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.9.0",
    "httpx>=0.27.0",
    "beautifulsoup4>=4.12.0",
    "lxml>=5.0.0",
    "pandas>=2.0.0",
    "rich>=13.0.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
browser = ["playwright>=1.40.0"]
dev = ["pytest>=8.0.0", "ruff>=0.1.0", "pytest-httpx>=0.30.0"]

[project.scripts]
ebay-tracker = "ebay_tracker.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Step 3: Create .gitignore**

Create `.gitignore`:

```
# Python
__pycache__/
*.py[cod]
*$py.class
.venv/
venv/
.env

# Project
data/
*.db

# IDE
.idea/
.vscode/
*.swp

# uv
.python-version
```

**Step 4: Create .env.example**

Create `.env.example`:

```
DECODO_PROXY_URL=http://user:pass@proxy.decodo.com:port
EBAY_TRACKER_DB_PATH=./data/ebay_tracker.db
```

**Step 5: Create directories**

Run:
```bash
mkdir -p tests/fixtures data
touch tests/__init__.py
```

**Step 6: Sync dependencies**

Run:
```bash
uv sync --dev
```

Expected: All dependencies installed, `.venv` created

**Step 7: Verify installation**

Run:
```bash
uv run python -c "import typer, httpx, bs4, pandas, rich; print('OK')"
```

Expected: `OK`

**Step 8: Commit**

```bash
git add -A
git commit -m "feat: initialize project with uv and dependencies"
```

---

## Task 2: Configuration Module

**Files:**
- Create: `src/ebay_tracker/config.py`
- Create: `tests/test_config.py`

**Step 1: Write failing test for config loading**

Create `tests/test_config.py`:

```python
import os
from pathlib import Path


def test_get_config_returns_defaults_when_no_env():
    # Clear any existing env vars
    os.environ.pop("DECODO_PROXY_URL", None)
    os.environ.pop("EBAY_TRACKER_DB_PATH", None)

    from ebay_tracker.config import get_config

    config = get_config()

    assert config.proxy_url is None
    assert config.db_path == Path("data/ebay_tracker.db")


def test_get_config_reads_from_env():
    os.environ["DECODO_PROXY_URL"] = "http://test:pass@proxy.example.com:8080"
    os.environ["EBAY_TRACKER_DB_PATH"] = "/custom/path/test.db"

    from ebay_tracker import config
    # Force reload
    import importlib
    importlib.reload(config)

    cfg = config.get_config()

    assert cfg.proxy_url == "http://test:pass@proxy.example.com:8080"
    assert cfg.db_path == Path("/custom/path/test.db")

    # Cleanup
    os.environ.pop("DECODO_PROXY_URL", None)
    os.environ.pop("EBAY_TRACKER_DB_PATH", None)
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_config.py -v
```

Expected: FAIL with `ModuleNotFoundError` or `ImportError`

**Step 3: Implement config module**

Create `src/ebay_tracker/config.py`:

```python
from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    proxy_url: str | None
    db_path: Path


def get_config() -> Config:
    return Config(
        proxy_url=os.environ.get("DECODO_PROXY_URL"),
        db_path=Path(os.environ.get("EBAY_TRACKER_DB_PATH", "data/ebay_tracker.db")),
    )
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_config.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/ebay_tracker/config.py tests/test_config.py
git commit -m "feat: add configuration module with env var support"
```

---

## Task 3: Data Models

**Files:**
- Create: `src/ebay_tracker/models.py`
- Create: `tests/test_models.py`

**Step 1: Write failing test for models**

Create `tests/test_models.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_models.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement models**

Create `src/ebay_tracker/models.py`:

```python
from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class Search:
    id: int | None
    name: str
    query: str
    filters: dict | None
    created_at: datetime | None
    last_fetched_at: datetime | None


@dataclass
class Listing:
    id: int | None
    search_id: int
    ebay_item_id: str
    title: str
    price: float
    shipping: float | None
    condition: str | None
    sold_date: date | None
    url: str | None
    created_at: datetime | None

    @property
    def total_price(self) -> float:
        return self.price + (self.shipping or 0)


@dataclass
class FetchLog:
    id: int | None
    search_id: int
    fetched_at: datetime | None
    listings_found: int
    status: str
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_models.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/ebay_tracker/models.py tests/test_models.py
git commit -m "feat: add data models for Search, Listing, FetchLog"
```

---

## Task 4: Database Layer

**Files:**
- Create: `src/ebay_tracker/db.py`
- Create: `tests/test_db.py`

**Step 1: Write failing tests for database**

Create `tests/test_db.py`:

```python
import pytest
from datetime import date, datetime
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
```

**Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/test_db.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement database module**

Create `src/ebay_tracker/db.py`:

```python
import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from ebay_tracker.models import Search, Listing, FetchLog


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: sqlite3.Connection | None = None

    def init(self) -> None:
        """Initialize database connection and create tables."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS searches (
                id              INTEGER PRIMARY KEY,
                name            TEXT NOT NULL UNIQUE,
                query           TEXT NOT NULL,
                filters         TEXT,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_fetched_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS listings (
                id              INTEGER PRIMARY KEY,
                search_id       INTEGER NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
                ebay_item_id    TEXT NOT NULL,
                title           TEXT NOT NULL,
                price           REAL NOT NULL,
                shipping        REAL,
                condition       TEXT,
                sold_date       DATE,
                url             TEXT,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(search_id, ebay_item_id)
            );

            CREATE TABLE IF NOT EXISTS fetch_log (
                id              INTEGER PRIMARY KEY,
                search_id       INTEGER NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
                fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                listings_found  INTEGER,
                status          TEXT
            );

            PRAGMA foreign_keys = ON;
        """)
        self.conn.commit()

    def add_search(self, search: Search) -> int:
        """Add a new search. Returns the search ID."""
        cursor = self.conn.execute(
            """
            INSERT INTO searches (name, query, filters)
            VALUES (?, ?, ?)
            """,
            (search.name, search.query, json.dumps(search.filters) if search.filters else None),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_search_by_name(self, name: str) -> Search | None:
        """Get a search by name."""
        cursor = self.conn.execute(
            "SELECT * FROM searches WHERE name = ?",
            (name,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_search(row)

    def get_search_by_id(self, search_id: int) -> Search | None:
        """Get a search by ID."""
        cursor = self.conn.execute(
            "SELECT * FROM searches WHERE id = ?",
            (search_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_search(row)

    def get_all_searches(self) -> list[Search]:
        """Get all searches."""
        cursor = self.conn.execute("SELECT * FROM searches ORDER BY created_at")
        return [self._row_to_search(row) for row in cursor.fetchall()]

    def delete_search(self, search_id: int) -> None:
        """Delete a search and all its listings."""
        # Enable foreign keys for this connection
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("DELETE FROM searches WHERE id = ?", (search_id,))
        self.conn.commit()

    def update_search_last_fetched(self, search_id: int) -> None:
        """Update the last_fetched_at timestamp for a search."""
        self.conn.execute(
            "UPDATE searches SET last_fetched_at = CURRENT_TIMESTAMP WHERE id = ?",
            (search_id,),
        )
        self.conn.commit()

    def add_listing(self, listing: Listing) -> int | None:
        """Add a listing. Returns listing ID or None if duplicate."""
        try:
            cursor = self.conn.execute(
                """
                INSERT INTO listings (search_id, ebay_item_id, title, price, shipping, condition, sold_date, url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    listing.search_id,
                    listing.ebay_item_id,
                    listing.title,
                    listing.price,
                    listing.shipping,
                    listing.condition,
                    listing.sold_date.isoformat() if listing.sold_date else None,
                    listing.url,
                ),
            )
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Duplicate listing, ignore
            return None

    def get_listings_for_search(self, search_id: int) -> list[Listing]:
        """Get all listings for a search."""
        cursor = self.conn.execute(
            "SELECT * FROM listings WHERE search_id = ? ORDER BY sold_date DESC",
            (search_id,),
        )
        return [self._row_to_listing(row) for row in cursor.fetchall()]

    def add_fetch_log(self, log: FetchLog) -> int:
        """Add a fetch log entry."""
        cursor = self.conn.execute(
            """
            INSERT INTO fetch_log (search_id, listings_found, status)
            VALUES (?, ?, ?)
            """,
            (log.search_id, log.listings_found, log.status),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_listing_count_for_search(self, search_id: int) -> int:
        """Get the number of listings for a search."""
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM listings WHERE search_id = ?",
            (search_id,),
        )
        return cursor.fetchone()[0]

    def _row_to_search(self, row: sqlite3.Row) -> Search:
        """Convert a database row to a Search model."""
        return Search(
            id=row["id"],
            name=row["name"],
            query=row["query"],
            filters=json.loads(row["filters"]) if row["filters"] else None,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            last_fetched_at=datetime.fromisoformat(row["last_fetched_at"]) if row["last_fetched_at"] else None,
        )

    def _row_to_listing(self, row: sqlite3.Row) -> Listing:
        """Convert a database row to a Listing model."""
        return Listing(
            id=row["id"],
            search_id=row["search_id"],
            ebay_item_id=row["ebay_item_id"],
            title=row["title"],
            price=row["price"],
            shipping=row["shipping"],
            condition=row["condition"],
            sold_date=date.fromisoformat(row["sold_date"]) if row["sold_date"] else None,
            url=row["url"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )
```

**Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/test_db.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/ebay_tracker/db.py tests/test_db.py
git commit -m "feat: add SQLite database layer with CRUD operations"
```

---

## Task 5: Scraper Module

**Files:**
- Create: `src/ebay_tracker/scraper.py`
- Create: `tests/test_scraper.py`
- Create: `tests/fixtures/ebay_sold_listings.html`

**Step 1: Create test fixture with sample eBay HTML**

Create `tests/fixtures/ebay_sold_listings.html`:

```html
<!DOCTYPE html>
<html>
<head><title>Test eBay Results</title></head>
<body>
<ul class="srp-results">
  <li class="s-item">
    <a class="s-item__link" href="https://www.ebay.com/itm/123456789?hash=item123">
      <div class="s-item__title">Levi's 501 Original Fit Jeans 32x30 Dark Wash</div>
    </a>
    <div class="s-item__details">
      <span class="s-item__price">$45.00</span>
      <span class="s-item__shipping s-item__logisticsCost">+$5.99 shipping</span>
      <span class="SECONDARY_INFO">Pre-owned</span>
      <span class="POSITIVE">Sold  Jan 10, 2025</span>
    </div>
  </li>
  <li class="s-item">
    <a class="s-item__link" href="https://www.ebay.com/itm/987654321?hash=item987">
      <div class="s-item__title">Levi's 501 Jeans 32x30 Medium Wash Men's</div>
    </a>
    <div class="s-item__details">
      <span class="s-item__price">$38.50</span>
      <span class="s-item__shipping s-item__logisticsCost">Free shipping</span>
      <span class="SECONDARY_INFO">Pre-owned</span>
      <span class="POSITIVE">Sold  Jan 8, 2025</span>
    </div>
  </li>
  <li class="s-item">
    <a class="s-item__link" href="https://www.ebay.com/itm/555555555?hash=item555">
      <div class="s-item__title">Levi's 501 Button Fly 32x30 Black</div>
    </a>
    <div class="s-item__details">
      <span class="s-item__price">$52.00</span>
      <span class="s-item__shipping s-item__logisticsCost">+$7.50 shipping</span>
      <span class="SECONDARY_INFO">New with tags</span>
      <span class="POSITIVE">Sold  Jan 5, 2025</span>
    </div>
  </li>
</ul>
</body>
</html>
```

**Step 2: Write failing tests for scraper**

Create `tests/test_scraper.py`:

```python
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
```

**Step 3: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/test_scraper.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 4: Implement scraper module**

Create `src/ebay_tracker/scraper.py`:

```python
import random
import re
import time
from datetime import date, datetime
from urllib.parse import urlencode, quote_plus

import httpx
from bs4 import BeautifulSoup

from ebay_tracker.models import Listing


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def build_search_url(query: str, filters: dict | None = None) -> str:
    """Build eBay sold listings search URL."""
    params = {
        "_nkw": query,
        "LH_Complete": "1",
        "LH_Sold": "1",
        "_ipg": "240",  # Max results per page
    }

    if filters:
        if "max_price" in filters:
            params["_udhi"] = str(filters["max_price"])
        if "min_price" in filters:
            params["_udlo"] = str(filters["min_price"])
        if "condition" in filters:
            condition = filters["condition"].lower()
            if condition == "new":
                params["LH_ItemCondition"] = "1000"
            elif condition in ("pre-owned", "used"):
                params["LH_ItemCondition"] = "3000"

    return f"https://www.ebay.com/sch/i.html?{urlencode(params)}"


def get_headers() -> dict:
    """Get randomized browser-like headers."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


def fetch_page(url: str, proxy_url: str | None = None) -> str:
    """Fetch a page through the proxy."""
    transport = None
    if proxy_url:
        transport = httpx.HTTPTransport(proxy=proxy_url)

    with httpx.Client(transport=transport, timeout=30.0, follow_redirects=True) as client:
        response = client.get(url, headers=get_headers())
        response.raise_for_status()
        return response.text


def parse_listings(html: str, search_id: int) -> list[Listing]:
    """Parse eBay search results HTML and extract listings."""
    soup = BeautifulSoup(html, "lxml")
    listings = []

    for item in soup.select("li.s-item"):
        # Skip "shop on eBay" promotional items
        title_elem = item.select_one(".s-item__title")
        if not title_elem:
            continue
        title = title_elem.get_text(strip=True)
        if title.lower() == "shop on ebay":
            continue

        # Extract URL and item ID
        link_elem = item.select_one("a.s-item__link")
        url = link_elem.get("href") if link_elem else None
        item_id = extract_item_id(url) if url else None
        if not item_id:
            continue

        # Extract price
        price_elem = item.select_one(".s-item__price")
        price_text = price_elem.get_text(strip=True) if price_elem else "0"
        price = parse_price(price_text)

        # Extract shipping
        shipping_elem = item.select_one(".s-item__shipping, .s-item__logisticsCost")
        shipping_text = shipping_elem.get_text(strip=True) if shipping_elem else "Free shipping"
        shipping = parse_shipping(shipping_text)

        # Extract condition
        condition_elem = item.select_one(".SECONDARY_INFO")
        condition = condition_elem.get_text(strip=True) if condition_elem else None

        # Extract sold date
        sold_elem = item.select_one(".POSITIVE")
        sold_text = sold_elem.get_text(strip=True) if sold_elem else None
        sold_date = parse_sold_date(sold_text) if sold_text else None

        listings.append(Listing(
            id=None,
            search_id=search_id,
            ebay_item_id=item_id,
            title=title,
            price=price,
            shipping=shipping,
            condition=condition,
            sold_date=sold_date,
            url=url,
            created_at=None,
        ))

    return listings


def extract_item_id(url: str) -> str | None:
    """Extract eBay item ID from URL."""
    if not url:
        return None
    match = re.search(r"/itm/(\d+)", url)
    return match.group(1) if match else None


def parse_price(text: str) -> float:
    """Parse price string to float."""
    # Remove currency symbol and commas
    cleaned = re.sub(r"[^\d.]", "", text)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_shipping(text: str) -> float:
    """Parse shipping cost string to float."""
    if "free" in text.lower():
        return 0.0
    return parse_price(text)


def parse_sold_date(text: str) -> date | None:
    """Parse sold date string to date object."""
    if not text:
        return None
    # Remove "Sold" prefix and extra whitespace
    cleaned = re.sub(r"^Sold\s+", "", text).strip()
    try:
        # Parse formats like "Jan 10, 2025"
        return datetime.strptime(cleaned, "%b %d, %Y").date()
    except ValueError:
        return None


def rate_limit_delay() -> None:
    """Random delay between requests to avoid detection."""
    time.sleep(random.uniform(2.0, 5.0))
```

**Step 5: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/test_scraper.py -v
```

Expected: All PASS

**Step 6: Commit**

```bash
git add src/ebay_tracker/scraper.py tests/test_scraper.py tests/fixtures/
git commit -m "feat: add eBay scraper with HTML parsing and proxy support"
```

---

## Task 6: Analyzer Module

**Files:**
- Create: `src/ebay_tracker/analyzer.py`
- Create: `tests/test_analyzer.py`

**Step 1: Write failing tests for analyzer**

Create `tests/test_analyzer.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/test_analyzer.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement analyzer module**

Create `src/ebay_tracker/analyzer.py`:

```python
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
```

**Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/test_analyzer.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/ebay_tracker/analyzer.py tests/test_analyzer.py
git commit -m "feat: add analyzer module with price stats and predictions"
```

---

## Task 7: CLI - Basic Commands

**Files:**
- Create: `src/ebay_tracker/cli.py`
- Update: `src/ebay_tracker/__init__.py`
- Create: `tests/test_cli.py`

**Step 1: Write failing tests for CLI**

Create `tests/test_cli.py`:

```python
import pytest
from typer.testing import CliRunner
from pathlib import Path
import tempfile
import os


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def temp_db(monkeypatch):
    """Use a temporary database for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        monkeypatch.setenv("EBAY_TRACKER_DB_PATH", str(db_path))
        yield db_path


def test_cli_help(runner):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "ebay-tracker" in result.stdout.lower() or "usage" in result.stdout.lower()


def test_cli_add_search(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["add", "Levi's 501 32x30"])

    assert result.exit_code == 0
    assert "added" in result.stdout.lower() or "Levi" in result.stdout


def test_cli_add_search_with_options(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, [
        "add", "Levi's 501 32x30",
        "--condition", "Pre-owned",
        "--max-price", "100"
    ])

    assert result.exit_code == 0


def test_cli_list_searches_empty(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "no searches" in result.stdout.lower() or result.stdout.strip() == ""


def test_cli_list_searches_with_items(runner, temp_db):
    from ebay_tracker.cli import app

    # Add a search first
    runner.invoke(app, ["add", "Levi's 501 32x30"])

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "Levi" in result.stdout


def test_cli_remove_search(runner, temp_db):
    from ebay_tracker.cli import app

    # Add then remove
    runner.invoke(app, ["add", "Levi's 501 32x30"])
    result = runner.invoke(app, ["remove", "Levi's 501 32x30"])

    assert result.exit_code == 0
    assert "removed" in result.stdout.lower() or "deleted" in result.stdout.lower()


def test_cli_remove_nonexistent(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["remove", "Nonexistent Search"])

    assert result.exit_code == 1 or "not found" in result.stdout.lower()


def test_cli_status(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
```

**Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/test_cli.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement CLI module**

Create `src/ebay_tracker/cli.py`:

```python
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ebay_tracker.config import get_config
from ebay_tracker.db import Database
from ebay_tracker.models import Search

app = typer.Typer(
    name="ebay-tracker",
    help="Track eBay sold listings and predict prices",
    no_args_is_help=True,
)
console = Console()


def get_db() -> Database:
    """Get database connection."""
    config = get_config()
    db = Database(config.db_path)
    db.init()
    return db


@app.command()
def add(
    name: str = typer.Argument(..., help="Name for this search"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="eBay search query (defaults to name)"),
    condition: Optional[str] = typer.Option(None, "--condition", "-c", help="Item condition filter"),
    min_price: Optional[float] = typer.Option(None, "--min-price", help="Minimum price filter"),
    max_price: Optional[float] = typer.Option(None, "--max-price", help="Maximum price filter"),
):
    """Add a new search to track."""
    db = get_db()

    # Check if already exists
    if db.get_search_by_name(name):
        console.print(f"[red]Search '{name}' already exists[/red]")
        raise typer.Exit(1)

    # Build filters
    filters = {}
    if condition:
        filters["condition"] = condition
    if min_price is not None:
        filters["min_price"] = min_price
    if max_price is not None:
        filters["max_price"] = max_price

    search = Search(
        id=None,
        name=name,
        query=query or name,
        filters=filters if filters else None,
        created_at=None,
        last_fetched_at=None,
    )

    db.add_search(search)
    db.close()

    console.print(f"[green]Added search:[/green] {name}")
    if filters:
        console.print(f"  Filters: {filters}")


@app.command("list")
def list_searches():
    """List all tracked searches."""
    db = get_db()
    searches = db.get_all_searches()

    if not searches:
        console.print("[dim]No searches tracked yet. Use 'add' to create one.[/dim]")
        db.close()
        return

    table = Table(title="Tracked Searches")
    table.add_column("Name", style="cyan")
    table.add_column("Query", style="dim")
    table.add_column("Listings", justify="right")
    table.add_column("Last Fetched", style="dim")

    for search in searches:
        count = db.get_listing_count_for_search(search.id)
        last_fetched = search.last_fetched_at.strftime("%Y-%m-%d %H:%M") if search.last_fetched_at else "Never"
        table.add_row(
            search.name,
            search.query if search.query != search.name else "-",
            str(count),
            last_fetched,
        )

    console.print(table)
    db.close()


@app.command()
def remove(
    name: str = typer.Argument(..., help="Name of search to remove"),
):
    """Remove a search and all its listings."""
    db = get_db()

    search = db.get_search_by_name(name)
    if not search:
        console.print(f"[red]Search '{name}' not found[/red]")
        db.close()
        raise typer.Exit(1)

    listing_count = db.get_listing_count_for_search(search.id)
    db.delete_search(search.id)
    db.close()

    console.print(f"[green]Removed search:[/green] {name}")
    if listing_count > 0:
        console.print(f"  [dim]Deleted {listing_count} listings[/dim]")


@app.command()
def status():
    """Show status of proxy and database."""
    config = get_config()

    console.print("[bold]eBay Tracker Status[/bold]")
    console.print()

    # Database status
    console.print(f"[cyan]Database:[/cyan] {config.db_path}")
    if config.db_path.exists():
        db = get_db()
        searches = db.get_all_searches()
        total_listings = sum(db.get_listing_count_for_search(s.id) for s in searches)
        console.print(f"  Searches: {len(searches)}")
        console.print(f"  Listings: {total_listings}")
        db.close()
    else:
        console.print("  [dim]Not initialized[/dim]")

    console.print()

    # Proxy status
    console.print(f"[cyan]Proxy:[/cyan]", end=" ")
    if config.proxy_url:
        # Mask credentials in URL
        masked = config.proxy_url.split("@")[-1] if "@" in config.proxy_url else config.proxy_url
        console.print(f"Configured ({masked})")
    else:
        console.print("[yellow]Not configured[/yellow]")
        console.print("  [dim]Set DECODO_PROXY_URL in .env[/dim]")


if __name__ == "__main__":
    app()
```

**Step 4: Update __init__.py**

Update `src/ebay_tracker/__init__.py`:

```python
"""eBay Tracker - Track sold listings and predict prices."""

__version__ = "0.1.0"
```

**Step 5: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/test_cli.py -v
```

Expected: All PASS

**Step 6: Test CLI manually**

Run:
```bash
uv run ebay-tracker --help
uv run ebay-tracker status
```

Expected: Help output and status display

**Step 7: Commit**

```bash
git add src/ebay_tracker/cli.py src/ebay_tracker/__init__.py tests/test_cli.py
git commit -m "feat: add CLI with add, list, remove, and status commands"
```

---

## Task 8: CLI - Fetch Command

**Files:**
- Modify: `src/ebay_tracker/cli.py`
- Update: `tests/test_cli.py`

**Step 1: Add test for fetch command**

Add to `tests/test_cli.py`:

```python
def test_cli_fetch_no_searches(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["fetch"])

    assert result.exit_code == 0
    assert "no searches" in result.stdout.lower()


def test_cli_fetch_specific_search_not_found(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["fetch", "Nonexistent"])

    assert result.exit_code == 1 or "not found" in result.stdout.lower()
```

**Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/test_cli.py::test_cli_fetch_no_searches -v
```

Expected: FAIL (no fetch command)

**Step 3: Add fetch command to CLI**

Add to `src/ebay_tracker/cli.py` after the imports:

```python
from ebay_tracker.scraper import build_search_url, fetch_page, parse_listings, rate_limit_delay
from ebay_tracker.models import Search, FetchLog
```

Add this command after the `status` command:

```python
@app.command()
def fetch(
    name: Optional[str] = typer.Argument(None, help="Name of search to fetch (all if not specified)"),
    days: int = typer.Option(90, "--days", "-d", help="How many days back to fetch"),
):
    """Fetch new listings from eBay."""
    config = get_config()
    db = get_db()

    if name:
        search = db.get_search_by_name(name)
        if not search:
            console.print(f"[red]Search '{name}' not found[/red]")
            db.close()
            raise typer.Exit(1)
        searches = [search]
    else:
        searches = db.get_all_searches()

    if not searches:
        console.print("[dim]No searches to fetch. Use 'add' to create one.[/dim]")
        db.close()
        return

    if not config.proxy_url:
        console.print("[yellow]Warning: No proxy configured. Requests may be blocked.[/yellow]")
        console.print("[dim]Set DECODO_PROXY_URL in .env for better reliability.[/dim]")
        console.print()

    total_new = 0

    for search in searches:
        console.print(f"[cyan]Fetching:[/cyan] {search.name}")

        try:
            url = build_search_url(search.query, search.filters)
            html = fetch_page(url, config.proxy_url)
            listings = parse_listings(html, search.id)

            new_count = 0
            for listing in listings:
                if db.add_listing(listing):
                    new_count += 1

            db.update_search_last_fetched(search.id)
            db.add_fetch_log(FetchLog(
                id=None,
                search_id=search.id,
                fetched_at=None,
                listings_found=len(listings),
                status="success",
            ))

            console.print(f"  Found {len(listings)} listings, {new_count} new")
            total_new += new_count

        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")
            db.add_fetch_log(FetchLog(
                id=None,
                search_id=search.id,
                fetched_at=None,
                listings_found=0,
                status=f"error: {e}",
            ))

        # Rate limit between searches
        if len(searches) > 1 and search != searches[-1]:
            rate_limit_delay()

    console.print()
    console.print(f"[green]Done![/green] {total_new} new listings added")
    db.close()
```

**Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/test_cli.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/ebay_tracker/cli.py tests/test_cli.py
git commit -m "feat: add fetch command to scrape eBay listings"
```

---

## Task 9: CLI - Analyze Command

**Files:**
- Modify: `src/ebay_tracker/cli.py`
- Update: `tests/test_cli.py`

**Step 1: Add tests for analyze command**

Add to `tests/test_cli.py`:

```python
def test_cli_analyze_no_data(runner, temp_db):
    from ebay_tracker.cli import app

    runner.invoke(app, ["add", "Test Search"])
    result = runner.invoke(app, ["analyze", "Test Search"])

    assert result.exit_code == 0
    assert "no data" in result.stdout.lower() or "0" in result.stdout


def test_cli_analyze_not_found(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["analyze", "Nonexistent"])

    assert result.exit_code == 1 or "not found" in result.stdout.lower()
```

**Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/test_cli.py::test_cli_analyze_no_data -v
```

Expected: FAIL (no analyze command)

**Step 3: Add analyze command to CLI**

Add to imports in `src/ebay_tracker/cli.py`:

```python
from ebay_tracker.analyzer import analyze_listings, get_recommendation
```

Add this command:

```python
@app.command()
def analyze(
    name: str = typer.Argument(..., help="Name of search to analyze"),
    target_price: Optional[float] = typer.Option(None, "--target-price", "-t", help="Target price for wait estimate"),
):
    """Analyze price statistics and get predictions."""
    db = get_db()

    search = db.get_search_by_name(name)
    if not search:
        console.print(f"[red]Search '{name}' not found[/red]")
        db.close()
        raise typer.Exit(1)

    listings = db.get_listings_for_search(search.id)

    if not listings:
        console.print(f"[yellow]{search.name}[/yellow] - No data")
        console.print("[dim]Run 'fetch' to collect listings first.[/dim]")
        db.close()
        return

    stats = analyze_listings(listings)
    rec = get_recommendation(listings, target_price)

    # Header
    console.print()
    console.print(f"[bold cyan]{search.name}[/bold cyan] ({stats['count']} sales tracked)")
    console.print()

    # Price stats
    price = stats["price"]
    console.print(
        f"[bold]Price:[/bold]      "
        f"${price['median']:.0f} median  |  "
        f"${price['min']:.0f}-{price['max']:.0f} range  |  "
        f"${price['mean']:.0f} avg"
    )

    # Frequency
    freq = stats["frequency"]
    if freq["avg_days_between"]:
        console.print(
            f"[bold]Frequency:[/bold]  "
            f"~1 listing every {freq['avg_days_between']:.0f} days"
        )

    # Trend
    console.print(f"[bold]Trend:[/bold]      {stats['trend'].capitalize()}")
    console.print()

    # Recommendation
    if rec.get("good_deal_threshold"):
        console.print(
            f"[green]Recommendation:[/green] A price under "
            f"${rec['good_deal_threshold']:.0f} is a good deal (bottom 20%)"
        )

    # Target price prediction
    if target_price and rec.get("expected_wait_days"):
        console.print(
            f"[green]Target ${target_price:.0f}:[/green] "
            f"~{rec['target_percentile']:.0f}th percentile, "
            f"expected wait ~{rec['expected_wait_days']:.0f} days"
        )

    db.close()
```

**Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/test_cli.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/ebay_tracker/cli.py tests/test_cli.py
git commit -m "feat: add analyze command with price stats and predictions"
```

---

## Task 10: CLI - History and Export Commands

**Files:**
- Modify: `src/ebay_tracker/cli.py`
- Update: `tests/test_cli.py`

**Step 1: Add tests for history and export**

Add to `tests/test_cli.py`:

```python
def test_cli_history_not_found(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["history", "Nonexistent"])

    assert result.exit_code == 1 or "not found" in result.stdout.lower()


def test_cli_history_empty(runner, temp_db):
    from ebay_tracker.cli import app

    runner.invoke(app, ["add", "Test Search"])
    result = runner.invoke(app, ["history", "Test Search"])

    assert result.exit_code == 0


def test_cli_export_not_found(runner, temp_db):
    from ebay_tracker.cli import app

    result = runner.invoke(app, ["export", "Nonexistent"])

    assert result.exit_code == 1 or "not found" in result.stdout.lower()
```

**Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/test_cli.py::test_cli_history_not_found -v
```

Expected: FAIL (no history command)

**Step 3: Add history and export commands**

Add to `src/ebay_tracker/cli.py`:

```python
import csv
from io import StringIO
```

Add these commands:

```python
@app.command()
def history(
    name: str = typer.Argument(..., help="Name of search to show history for"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of listings to show"),
):
    """Show listing history for a search."""
    db = get_db()

    search = db.get_search_by_name(name)
    if not search:
        console.print(f"[red]Search '{name}' not found[/red]")
        db.close()
        raise typer.Exit(1)

    listings = db.get_listings_for_search(search.id)

    if not listings:
        console.print(f"[yellow]{search.name}[/yellow] - No listings")
        console.print("[dim]Run 'fetch' to collect listings first.[/dim]")
        db.close()
        return

    table = Table(title=f"Recent Sales: {search.name}")
    table.add_column("Date", style="dim")
    table.add_column("Title")
    table.add_column("Price", justify="right", style="green")
    table.add_column("Ship", justify="right", style="dim")
    table.add_column("Condition", style="dim")

    for listing in listings[:limit]:
        date_str = listing.sold_date.strftime("%Y-%m-%d") if listing.sold_date else "-"
        title = listing.title[:50] + "..." if len(listing.title) > 50 else listing.title
        shipping = f"${listing.shipping:.2f}" if listing.shipping else "Free"

        table.add_row(
            date_str,
            title,
            f"${listing.price:.2f}",
            shipping,
            listing.condition or "-",
        )

    console.print(table)

    if len(listings) > limit:
        console.print(f"[dim]Showing {limit} of {len(listings)} listings. Use --limit to see more.[/dim]")

    db.close()


@app.command()
def export(
    name: str = typer.Argument(..., help="Name of search to export"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path (default: stdout)"),
):
    """Export listings to CSV."""
    db = get_db()

    search = db.get_search_by_name(name)
    if not search:
        console.print(f"[red]Search '{name}' not found[/red]")
        db.close()
        raise typer.Exit(1)

    listings = db.get_listings_for_search(search.id)

    if not listings:
        console.print(f"[yellow]{search.name}[/yellow] - No listings to export")
        db.close()
        return

    # Build CSV
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "title", "price", "shipping", "total", "condition", "url", "ebay_item_id"])

    for listing in listings:
        writer.writerow([
            listing.sold_date.isoformat() if listing.sold_date else "",
            listing.title,
            listing.price,
            listing.shipping or 0,
            listing.total_price,
            listing.condition or "",
            listing.url or "",
            listing.ebay_item_id,
        ])

    csv_content = buffer.getvalue()

    if output:
        output.write_text(csv_content)
        console.print(f"[green]Exported {len(listings)} listings to {output}[/green]")
    else:
        print(csv_content)

    db.close()
```

**Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/test_cli.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/ebay_tracker/cli.py tests/test_cli.py
git commit -m "feat: add history and export commands"
```

---

## Task 11: Integration Test

**Files:**
- Create: `tests/test_integration.py`

**Step 1: Write integration test**

Create `tests/test_integration.py`:

```python
"""Integration tests for end-to-end workflows."""

import pytest
from typer.testing import CliRunner
from pathlib import Path
import tempfile


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def temp_env(monkeypatch):
    """Set up temporary environment for integration tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        monkeypatch.setenv("EBAY_TRACKER_DB_PATH", str(db_path))
        # Don't set proxy - we'll mock the scraper
        monkeypatch.delenv("DECODO_PROXY_URL", raising=False)
        yield tmpdir


def test_full_workflow_with_mock_data(runner, temp_env, monkeypatch):
    """Test complete workflow: add -> (mock) fetch -> analyze."""
    from ebay_tracker.cli import app
    from ebay_tracker import scraper
    from ebay_tracker.models import Listing
    from datetime import date

    # Mock the fetch_page function to return test data
    def mock_fetch_page(url, proxy_url=None):
        return """
        <ul class="srp-results">
          <li class="s-item">
            <a class="s-item__link" href="https://www.ebay.com/itm/111111111">
              <div class="s-item__title">Test Item 1</div>
            </a>
            <span class="s-item__price">$30.00</span>
            <span class="s-item__shipping">Free shipping</span>
            <span class="SECONDARY_INFO">Pre-owned</span>
            <span class="POSITIVE">Sold  Jan 1, 2025</span>
          </li>
          <li class="s-item">
            <a class="s-item__link" href="https://www.ebay.com/itm/222222222">
              <div class="s-item__title">Test Item 2</div>
            </a>
            <span class="s-item__price">$50.00</span>
            <span class="s-item__shipping">+$5.00 shipping</span>
            <span class="SECONDARY_INFO">Pre-owned</span>
            <span class="POSITIVE">Sold  Jan 10, 2025</span>
          </li>
          <li class="s-item">
            <a class="s-item__link" href="https://www.ebay.com/itm/333333333">
              <div class="s-item__title">Test Item 3</div>
            </a>
            <span class="s-item__price">$40.00</span>
            <span class="s-item__shipping">Free shipping</span>
            <span class="SECONDARY_INFO">New</span>
            <span class="POSITIVE">Sold  Jan 20, 2025</span>
          </li>
        </ul>
        """

    monkeypatch.setattr(scraper, "fetch_page", mock_fetch_page)
    monkeypatch.setattr(scraper, "rate_limit_delay", lambda: None)

    # 1. Add a search
    result = runner.invoke(app, ["add", "Test Search"])
    assert result.exit_code == 0
    assert "Added" in result.stdout or "added" in result.stdout.lower()

    # 2. List searches
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "Test Search" in result.stdout

    # 3. Fetch listings
    result = runner.invoke(app, ["fetch", "Test Search"])
    assert result.exit_code == 0
    assert "3" in result.stdout  # Found 3 listings

    # 4. Analyze
    result = runner.invoke(app, ["analyze", "Test Search"])
    assert result.exit_code == 0
    assert "3 sales" in result.stdout.lower() or "(3" in result.stdout
    assert "$40" in result.stdout  # Median price

    # 5. Analyze with target price
    result = runner.invoke(app, ["analyze", "Test Search", "--target-price", "35"])
    assert result.exit_code == 0

    # 6. History
    result = runner.invoke(app, ["history", "Test Search"])
    assert result.exit_code == 0
    assert "Test Item" in result.stdout

    # 7. Export
    result = runner.invoke(app, ["export", "Test Search"])
    assert result.exit_code == 0
    assert "111111111" in result.stdout  # Item ID in CSV

    # 8. Remove
    result = runner.invoke(app, ["remove", "Test Search"])
    assert result.exit_code == 0
    assert "Removed" in result.stdout or "removed" in result.stdout.lower()

    # 9. Verify removed
    result = runner.invoke(app, ["list"])
    assert "Test Search" not in result.stdout or "No searches" in result.stdout
```

**Step 2: Run integration test**

Run:
```bash
uv run pytest tests/test_integration.py -v
```

Expected: All PASS

**Step 3: Run all tests**

Run:
```bash
uv run pytest -v
```

Expected: All tests PASS

**Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration test for full workflow"
```

---

## Task 12: Final Touches

**Files:**
- Update: `.env.example`
- Create: `.env` (local only, not committed)

**Step 1: Verify .env.example is complete**

Verify `.env.example` contains:

```
DECODO_PROXY_URL=http://user:pass@proxy.decodo.com:port
EBAY_TRACKER_DB_PATH=./data/ebay_tracker.db
```

**Step 2: Create local .env file**

Create `.env` with your actual Decodo credentials:

```
DECODO_PROXY_URL=<your-actual-decodo-url>
EBAY_TRACKER_DB_PATH=./data/ebay_tracker.db
```

**Step 3: Test with real proxy**

Run:
```bash
uv run ebay-tracker status
uv run ebay-tracker add "Levi's 501 32x30"
uv run ebay-tracker fetch "Levi's 501 32x30"
uv run ebay-tracker analyze "Levi's 501 32x30"
```

**Step 4: Run linter**

Run:
```bash
uv run ruff check src/ tests/
```

Fix any issues if found.

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup and verification"
```

---

## Summary

After completing all tasks you will have:

1. **Project setup** with uv, dependencies, and configuration
2. **Data models** for Search, Listing, and FetchLog
3. **SQLite database layer** with CRUD operations
4. **eBay scraper** with proxy support and HTML parsing
5. **Analyzer** with price statistics and predictions
6. **Full CLI** with commands: add, list, remove, status, fetch, analyze, history, export
7. **Test suite** with unit and integration tests

Total: ~12 tasks, each with 5-8 steps following TDD approach.
