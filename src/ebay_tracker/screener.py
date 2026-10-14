"""Niche screener: rank brand/model niches by how ripe eBay-to-eBay flips are,
then scan live listings in the best niches for ones priced under what they sell for."""

import hashlib
import re
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd

from ebay_tracker.comps import is_junk_title, matches_brand, remove_price_outliers
from ebay_tracker.config import FeeConfig, ThresholdConfig
from ebay_tracker.fees import eBayFeeCalculator
from ebay_tracker.models import ActiveCard, Listing
from ebay_tracker.scraper import (
    build_search_url,
    parse_active_cards,
    parse_listings,
    parse_result_count,
)

Fetch = Callable[[str], str]

# eBay's sold search shows roughly the last 90 days of sales
SOLD_WINDOW_DAYS = 90
FULL_PAGE = 240
DEFAULT_FILTERS = {"condition": "pre-owned"}
AUCTION_HORIZON_HOURS = 24.0


@dataclass
class Gates:
    min_sold_90d: int = 15
    min_str_pct: float = 40.0
    min_brand_match_pct: float = 70.0
    min_median_price: float = 40.0


@dataclass
class Seed:
    name: str
    query: str
    brand: list[str]
    kind: str
    ship_cost: float
    filters: dict = field(default_factory=dict)
    alt_queries: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    keep: list[str] = field(default_factory=list)

    @property
    def athletic_shoes(self) -> bool:
        return self.kind == "sneakers"

    @property
    def search_filters(self) -> dict:
        return {**DEFAULT_FILTERS, **self.filters}


@dataclass
class NicheStats:
    name: str
    query: str
    kind: str
    sold_90d: int
    active_now: int | None
    str_pct: float | None
    sales_per_week: float
    cards_parsed: int
    comps_used: int
    brand_match_pct: float
    best_offer_share: float
    p20: float | None
    p25: float | None
    p50: float | None
    p75: float | None
    spread_pct: float | None
    median_buyer_shipping: float
    net_at_p50: float | None
    net_at_p25: float | None
    buy_ceiling: float | None
    headroom: float | None
    # Sold comps whose price + shipping was at or under the buy ceiling: buys that
    # would have cleared the profit thresholds had you caught them
    deal_share_pct: float = 0.0
    mean_deal_margin: float | None = None
    profit_pool_week: float = 0.0
    gate_failures: list[str] = field(default_factory=list)
    score: float | None = None

    @property
    def passes(self) -> bool:
        return not self.gate_failures


@dataclass
class Candidate:
    niche: str
    item_id: str
    title: str
    url: str
    price: float
    shipping: float | None
    total_cost: float
    is_auction: bool
    bid_count: int | None
    time_left: str | None
    buy_ceiling: float
    profit_at_p50: float
    profit_at_p25: float
    action: str  # "buy" (fixed price) or "watch" (auction: current bid is only a floor)
    source_query: str


def load_seeds(path: str | Path) -> list[Seed]:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    ship_defaults = data.get("ship_cost", {})
    seeds = []
    for row in data["seed"]:
        brand = row["brand"]
        seeds.append(Seed(
            name=row["name"],
            query=row["query"],
            brand=[brand] if isinstance(brand, str) else list(brand),
            kind=row["kind"],
            ship_cost=float(row.get("ship_cost", ship_defaults.get(row["kind"], 10.0))),
            filters=dict(row.get("filters", {})),
            alt_queries=list(row.get("alt_queries", [])),
            exclude=list(row.get("exclude", [])),
            keep=list(row.get("keep", [])),
        ))
    return seeds


def _calculator(seed: Seed, fee_cfg: FeeConfig) -> eBayFeeCalculator:
    return eBayFeeCalculator(
        final_value_pct=fee_cfg.final_value_pct,
        payment_processing_pct=fee_cfg.payment_processing_pct,
        payment_processing_flat=fee_cfg.payment_processing_flat,
        shipping_cost=seed.ship_cost,
        sales_tax_rate=fee_cfg.sales_tax_rate,
        buyer_tax_rate=fee_cfg.buyer_tax_rate,
        athletic_shoes=seed.athletic_shoes,
    )


def buy_ceiling(net_proceeds: float, thresholds: ThresholdConfig, purchase_tax_rate: float) -> float:
    """Highest listing price + shipping that still clears the profit thresholds.

    All-in cost C = listing total * (1 + tax). The thresholds need
    net - C >= min_dollar and (net - C) / C >= min_pct, i.e. C <= net - min_dollar
    and C <= net / (1 + min_pct). AND mode needs both, OR mode either.
    """
    by_dollar = net_proceeds - thresholds.min_profit_dollar
    by_pct = net_proceeds / (1 + thresholds.min_profit_pct / 100)
    all_in = max(by_dollar, by_pct) if thresholds.mode == "or" else min(by_dollar, by_pct)
    return round(all_in / (1 + purchase_tax_rate / 100), 2)


def _clean_comps(seed: Seed, cards: list) -> list:
    return [
        c for c in cards
        if matches_brand(c.title, seed.brand) and not is_junk_title(c.title, seed.exclude, seed.keep)
    ]


def _weekly_sales(sold_count: int | None, comps: list[Listing], cards_parsed: int,
                  clean_fraction: float) -> tuple[int, float]:
    """Sold volume over the window and per week.

    Prefer the page's result count (scaled by the share of cards that are clean comps).
    Without it, fall back to parsed comps over the span they cover.
    """
    if sold_count is not None:
        sold = round(sold_count * clean_fraction)
        return sold, round(sold / (SOLD_WINDOW_DAYS / 7), 2)
    dated = sorted(c.sold_date for c in comps if c.sold_date)
    span_days = SOLD_WINDOW_DAYS
    if cards_parsed >= FULL_PAGE and len(dated) >= 2:
        span_days = max(7, (dated[-1] - dated[0]).days)
    return len(comps), round(len(comps) / (span_days / 7), 2)


def compute_niche_stats(
    seed: Seed,
    sold_cards: list[Listing],
    sold_count: int | None,
    active_cards: list[ActiveCard] | None,
    active_count: int | None,
    fee_cfg: FeeConfig,
    thresholds: ThresholdConfig,
    gates: Gates | None = None,
) -> NicheStats:
    gates = gates or Gates()
    cards_parsed = len(sold_cards)
    brand_hits = sum(1 for c in sold_cards if matches_brand(c.title, seed.brand))
    brand_match_pct = round(brand_hits / cards_parsed * 100, 1) if cards_parsed else 0.0

    comps = _clean_comps(seed, sold_cards)
    clean_fraction = len(comps) / cards_parsed if cards_parsed else 0.0
    best_offer_share = (
        round(sum(1 for c in comps if c.best_offer_accepted) / len(comps) * 100, 1) if comps else 0.0
    )
    # Accepted offers show the asking price, so they count toward volume but not price
    priced = remove_price_outliers([c for c in comps if not c.best_offer_accepted])

    sold_90d, sales_per_week = _weekly_sales(sold_count, comps, cards_parsed, clean_fraction)

    active_now = None
    if active_count is not None:
        active_fraction = 1.0
        if active_cards:
            active_fraction = len(_clean_comps(seed, active_cards)) / len(active_cards)
        active_now = round(active_count * active_fraction)
    str_pct = None
    if active_now is not None and (sold_90d + active_now) > 0:
        str_pct = round(sold_90d / (sold_90d + active_now) * 100, 1)

    p20 = p25 = p50 = p75 = spread_pct = None
    net_p50 = net_p25 = ceiling = headroom = mean_margin = None
    deal_share_pct = profit_pool_week = 0.0
    shipping = [c.shipping for c in priced if c.shipping is not None]
    median_ship = float(pd.Series(shipping).median()) if shipping else 0.0
    if priced:
        prices = pd.Series([c.price for c in priced])
        p20, p25, p50, p75 = (round(float(prices.quantile(q)), 2) for q in (0.20, 0.25, 0.50, 0.75))
        spread_pct = round((p75 - p25) / p50 * 100, 1) if p50 else None
        calc = _calculator(seed, fee_cfg)
        net_p50 = calc.calculate_net_proceeds(p50, median_ship).net
        net_p25 = calc.calculate_net_proceeds(p25, median_ship).net
        ceiling = buy_ceiling(net_p50, thresholds, fee_cfg.sales_tax_rate)
        headroom = round(ceiling - (p20 + median_ship), 2)
        tax = 1 + fee_cfg.sales_tax_rate / 100
        deal_costs = [c.total_price * tax for c in priced if c.total_price <= ceiling]
        deal_share_pct = round(len(deal_costs) / len(priced) * 100, 1)
        if deal_costs:
            mean_margin = round(net_p50 - sum(deal_costs) / len(deal_costs), 2)
            profit_pool_week = round(sales_per_week * deal_share_pct / 100 * mean_margin, 1)

    failures = []
    if sold_90d < gates.min_sold_90d:
        failures.append(f"sold_90d {sold_90d} < {gates.min_sold_90d}")
    if str_pct is None:
        failures.append("no active count")
    elif str_pct < gates.min_str_pct:
        failures.append(f"STR {str_pct}% < {gates.min_str_pct}%")
    if brand_match_pct < gates.min_brand_match_pct:
        failures.append(f"brand match {brand_match_pct}% < {gates.min_brand_match_pct}%")
    if p50 is None or p50 < gates.min_median_price:
        failures.append(f"median {p50} < ${gates.min_median_price:.0f}")
    if p50 is not None and deal_share_pct == 0:
        failures.append("no sold comps under buy ceiling")

    score = profit_pool_week if not failures else None

    return NicheStats(
        name=seed.name, query=seed.query, kind=seed.kind,
        sold_90d=sold_90d, active_now=active_now, str_pct=str_pct,
        sales_per_week=sales_per_week, cards_parsed=cards_parsed, comps_used=len(priced),
        brand_match_pct=brand_match_pct, best_offer_share=best_offer_share,
        p20=p20, p25=p25, p50=p50, p75=p75, spread_pct=spread_pct,
        median_buyer_shipping=round(median_ship, 2),
        net_at_p50=net_p50, net_at_p25=net_p25, buy_ceiling=ceiling, headroom=headroom,
        deal_share_pct=deal_share_pct, mean_deal_margin=mean_margin,
        profit_pool_week=profit_pool_week, gate_failures=failures, score=score,
    )


def rank(stats: list[NicheStats]) -> list[NicheStats]:
    """Passing niches by score (profit pool per week), then the rest by profit pool,
    so gate failures stay visible."""
    passing = sorted((s for s in stats if s.passes), key=lambda s: s.score or 0, reverse=True)
    failing = sorted((s for s in stats if not s.passes), key=lambda s: s.profit_pool_week, reverse=True)
    return passing + failing


def parse_time_left_hours(text: str | None) -> float | None:
    """'1d 3h left' -> 27.0, '45m left' -> 0.75."""
    if not text:
        return None
    units = {"d": 24.0, "h": 1.0, "m": 1 / 60, "s": 1 / 3600}
    parts = re.findall(r"(\d+)\s*([dhms])\b", text.lower())
    if not parts:
        return None
    return round(sum(int(n) * units[u] for n, u in parts), 2)


def find_candidates(
    seed: Seed,
    stats: NicheStats,
    cards: list[ActiveCard],
    fee_cfg: FeeConfig,
    source_query: str = "",
    horizon_hours: float = AUCTION_HORIZON_HOURS,
) -> list[Candidate]:
    """Live listings whose price + shipping is at or under the niche's buy ceiling."""
    if stats.buy_ceiling is None or stats.net_at_p50 is None:
        return []
    tax = 1 + fee_cfg.sales_tax_rate / 100
    out = []
    for card in _clean_comps(seed, cards):
        if card.price <= 0 or card.total_cost > stats.buy_ceiling:
            continue
        if card.is_auction:
            hours = parse_time_left_hours(card.time_left)
            if hours is None or hours > horizon_hours:
                continue
        all_in = card.total_cost * tax
        out.append(Candidate(
            niche=seed.name, item_id=card.item_id, title=card.title, url=card.url,
            price=card.price, shipping=card.shipping, total_cost=round(card.total_cost, 2),
            is_auction=card.is_auction, bid_count=card.bid_count, time_left=card.time_left,
            buy_ceiling=stats.buy_ceiling,
            profit_at_p50=round(stats.net_at_p50 - all_in, 2),
            profit_at_p25=round((stats.net_at_p25 or 0) - all_in, 2),
            action="watch" if card.is_auction else "buy",
            source_query=source_query or seed.query,
        ))
    return out


# --- Fetch-driven parts ---


def niche_urls(seed: Seed) -> dict[str, str]:
    return {
        "sold": build_search_url(seed.query, seed.search_filters),
        "active": build_search_url(seed.query, seed.search_filters, sold=False),
    }


def listing_scan_urls(seed: Seed) -> list[tuple[str, str]]:
    """(query, url) pairs: newest and cheapest Buy It Now, auctions ending soonest,
    plus newest Buy It Now for each misspelling."""
    f = seed.search_filters
    urls = [
        (seed.query, build_search_url(seed.query, f, sold=False, buying_format="bin", sort="newly_listed")),
        (seed.query, build_search_url(seed.query, f, sold=False, buying_format="bin", sort="price_low")),
        (seed.query, build_search_url(seed.query, f, sold=False, buying_format="auction", sort="ending_soonest")),
    ]
    for alt in seed.alt_queries:
        urls.append((alt, build_search_url(alt, f, sold=False, buying_format="bin", sort="newly_listed")))
    return urls


def screen_niche(
    seed: Seed,
    fetch: Fetch,
    fee_cfg: FeeConfig,
    thresholds: ThresholdConfig,
    gates: Gates | None = None,
) -> NicheStats:
    urls = niche_urls(seed)
    sold_html = fetch(urls["sold"])
    active_html = fetch(urls["active"])
    return compute_niche_stats(
        seed,
        sold_cards=parse_listings(sold_html, search_id=0),
        sold_count=parse_result_count(sold_html),
        active_cards=parse_active_cards(active_html),
        active_count=parse_result_count(active_html),
        fee_cfg=fee_cfg,
        thresholds=thresholds,
        gates=gates,
    )


def scan_listings(seed: Seed, stats: NicheStats, fetch: Fetch, fee_cfg: FeeConfig) -> list[Candidate]:
    seen: set[str] = set()
    out = []
    for query, url in listing_scan_urls(seed):
        # Misspelled titles won't contain the brand spelled right, so match the alt query instead
        match_seed = seed if query == seed.query else Seed(
            name=seed.name, query=query, brand=[query.split()[0]], kind=seed.kind,
            ship_cost=seed.ship_cost, exclude=seed.exclude, keep=seed.keep,
        )
        for cand in find_candidates(match_seed, stats, parse_active_cards(fetch(url)), fee_cfg, query):
            if cand.item_id not in seen:
                seen.add(cand.item_id)
                out.append(cand)
    return sorted(out, key=lambda c: c.profit_at_p50, reverse=True)


def cached_fetch(fetch: Fetch, cache_dir: Path) -> tuple[Fetch, dict]:
    """Wrap fetch so each URL is fetched once per cache dir. Returns (fetch, counters)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    counters = {"fetched": 0, "cached": 0, "bytes": 0}

    def _fetch(url: str) -> str:
        path = cache_dir / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".html")
        if path.exists():
            counters["cached"] += 1
            return path.read_text(encoding="utf-8")
        html = fetch(url)
        path.write_text(html, encoding="utf-8")
        with (cache_dir / "index.tsv").open("a", encoding="utf-8") as idx:
            idx.write(f"{path.name}\t{url}\n")
        counters["fetched"] += 1
        counters["bytes"] += len(html.encode())
        return html

    return _fetch, counters


def default_cache_dir(root: Path = Path("data/scans")) -> Path:
    return root / date.today().isoformat()
