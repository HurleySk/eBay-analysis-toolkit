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


@dataclass
class ActiveListing:
    item_id: str
    title: str
    price: float
    shipping: float | None
    condition: str | None
    category_id: int | None
    item_specifics: dict
    url: str
    seller: str | None

    @property
    def total_cost(self) -> float:
        return self.price + (self.shipping or 0)


@dataclass
class SuggestedQuery:
    query: str
    filters: dict
    raw_attributes: dict


@dataclass
class NetProceeds:
    gross: float
    final_value_fee: float
    payment_processing_fee: float
    shipping_cost: float
    total_fees: float
    net: float


@dataclass
class SellTimePrediction:
    median_days: float
    fast_days: float
    slow_days: float
    ninety_pct_days: float
    confidence: str
    sample_size: int
    price_tier: str


@dataclass
class ProfitAnalysis:
    purchase_price: float
    purchase_shipping: float
    purchase_tax: float
    total_purchase_cost: float
    expected_sale_price: float
    sale_price_25th: float
    sale_price_75th: float
    net_proceeds: NetProceeds
    projected_profit: float
    projected_profit_pct: float
    meets_threshold: bool
    threshold_detail: str
    time_to_sell: SellTimePrediction | None
    confidence: str
    comp_count: int
    comps: list["Listing"]
