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
