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
