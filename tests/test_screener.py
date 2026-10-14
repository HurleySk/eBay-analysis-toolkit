from datetime import date, timedelta

import pytest

from ebay_tracker.config import FeeConfig, ThresholdConfig
from ebay_tracker.fees import eBayFeeCalculator
from ebay_tracker.models import ActiveCard, Listing
from ebay_tracker.screener import (
    Gates,
    NicheStats,
    Seed,
    buy_ceiling,
    compute_niche_stats,
    find_candidates,
    load_seeds,
    parse_time_left_hours,
    rank,
    scan_listings,
    screen_niche,
)

NO_TAX = FeeConfig(buyer_tax_rate=0.0)
THRESHOLDS = ThresholdConfig(min_profit_pct=20.0, min_profit_dollar=10.0, mode="and")


def _seed(**kw):
    defaults = dict(name="Alden Indy", query="Alden Indy", brand=["Alden"], kind="boots", ship_cost=14.0)
    return Seed(**{**defaults, **kw})


def _sold(prices, title="Alden Indy 405 boot 10D", best_offer=None, shipping=0.0):
    best_offer = best_offer or set()
    start = date(2026, 9, 1)
    return [
        Listing(
            id=None, search_id=0, ebay_item_id=str(i), title=title, price=p, shipping=shipping,
            condition="Pre-owned", sold_date=start + timedelta(days=i), url=None, created_at=None,
            best_offer_accepted=i in best_offer,
        )
        for i, p in enumerate(prices)
    ]


def _card(item_id, price, title="Alden Indy 405 boot", shipping=0.0, auction=False, time_left=None):
    return ActiveCard(
        item_id=item_id, title=title, price=price, shipping=shipping, condition="Pre-owned",
        url=f"https://www.ebay.com/itm/{item_id}", is_auction=auction,
        bid_count=3 if auction else None, time_left=time_left,
    )


def _stats(**kw):
    sold = _sold([150.0 + 10 * i for i in range(30)])
    stats = compute_niche_stats(_seed(), sold, 60, None, 40, NO_TAX, THRESHOLDS)
    for k, v in kw.items():
        setattr(stats, k, v)
    return stats


def test_sell_through_rate():
    stats = compute_niche_stats(_seed(), _sold([300.0] * 30), 60, None, 40, NO_TAX, THRESHOLDS)
    assert stats.sold_90d == 60
    assert stats.active_now == 40
    assert stats.str_pct == pytest.approx(60.0)
    assert stats.sales_per_week == pytest.approx(60 / (90 / 7), abs=0.01)


def test_sold_and_active_counts_scaled_by_clean_share():
    sold = _sold([300.0] * 20) + _sold([50.0] * 20, title="Generic indy boot")
    active = [_card(str(i), 300.0) for i in range(5)] + [_card(str(9 + i), 80.0, title="Indy boot") for i in range(15)]
    stats = compute_niche_stats(_seed(), sold, 100, active, 200, NO_TAX, THRESHOLDS)
    assert stats.brand_match_pct == 50.0
    assert stats.sold_90d == 50
    assert stats.active_now == 50


def test_best_offer_comps_excluded_from_price_stats():
    prices = [200.0] * 10 + [400.0] * 10
    sold = _sold(prices, best_offer=set(range(10, 20)))
    stats = compute_niche_stats(_seed(), sold, 20, None, 10, NO_TAX, THRESHOLDS)
    assert stats.p50 == 200.0
    assert stats.best_offer_share == 50.0
    assert stats.sold_90d == 20  # still counted toward volume


def test_junk_titles_dropped_from_comps():
    sold = _sold([300.0] * 10) + _sold([40.0] * 5, title="Alden shoe trees lot")
    stats = compute_niche_stats(_seed(), sold, 15, None, 5, NO_TAX, THRESHOLDS)
    assert stats.comps_used == 10
    assert stats.p20 == 300.0


def test_keep_terms_retain_unisex_titles():
    seed = _seed(keep=["women", "womens", "women's"])
    sold = _sold([150.0] * 10, title="Alden boot Men's 9 / Women's 11")
    stats = compute_niche_stats(seed, sold, 10, None, 5, NO_TAX, THRESHOLDS)
    assert stats.comps_used == 10


def test_buy_ceiling_matches_fee_calculator():
    calc = eBayFeeCalculator(shipping_cost=14.0, buyer_tax_rate=0.0)
    net = calc.calculate_net_proceeds(300.0).net
    ceiling = buy_ceiling(net, THRESHOLDS, purchase_tax_rate=0.0)
    profit = net - ceiling
    assert profit >= THRESHOLDS.min_profit_dollar - 0.01
    assert profit / ceiling * 100 == pytest.approx(THRESHOLDS.min_profit_pct, abs=0.05)


def test_buy_ceiling_or_mode_takes_looser_bound():
    and_ceiling = buy_ceiling(100.0, ThresholdConfig(20.0, 10.0, "and"), 0.0)
    or_ceiling = buy_ceiling(100.0, ThresholdConfig(20.0, 10.0, "or"), 0.0)
    assert and_ceiling == pytest.approx(100 / 1.2, abs=0.01)
    assert or_ceiling == pytest.approx(90.0, abs=0.01)


def test_buy_ceiling_accounts_for_purchase_tax():
    assert buy_ceiling(120.0, THRESHOLDS, 0.0) > buy_ceiling(120.0, THRESHOLDS, 8.0)


def test_gates_mark_reason():
    stats = compute_niche_stats(_seed(), _sold([30.0] * 5), 5, None, 100, NO_TAX, THRESHOLDS)
    joined = " | ".join(stats.gate_failures)
    assert "sold_90d" in joined
    assert "STR" in joined
    assert "median" in joined
    assert stats.score is None
    assert not stats.passes


def test_missing_active_count_fails_gate():
    stats = compute_niche_stats(_seed(), _sold([300.0] * 30), 60, None, None, NO_TAX, THRESHOLDS)
    assert "no active count" in stats.gate_failures


def test_deal_share_counts_sold_comps_under_ceiling():
    stats = _stats()
    prices = [150.0 + 10 * i for i in range(30)]
    under = [p for p in prices if p <= stats.buy_ceiling]
    assert stats.deal_share_pct == pytest.approx(len(under) / 30 * 100, abs=0.1)
    assert stats.mean_deal_margin == pytest.approx(stats.net_at_p50 - sum(under) / len(under), abs=0.01)


def test_score_is_profit_pool_per_week():
    stats = _stats()
    assert stats.passes
    expected = stats.sales_per_week * stats.deal_share_pct / 100 * stats.mean_deal_margin
    assert stats.score == pytest.approx(expected, abs=0.1)


def test_tight_price_band_has_no_deals():
    # Everything sells within a few dollars: no sold price leaves room for fees + profit
    stats = compute_niche_stats(_seed(), _sold([300.0 + i for i in range(30)]), 60, None, 40, NO_TAX, THRESHOLDS)
    assert stats.deal_share_pct == 0
    assert "no sold comps under buy ceiling" in stats.gate_failures
    assert stats.headroom < 0


def test_rank_orders_by_profit_pool():
    def ns(name, score, failures=(), pool=10.0):
        return NicheStats(
            name=name, query=name, kind="boots", sold_90d=50, active_now=10, str_pct=80.0,
            sales_per_week=4.0, cards_parsed=50, comps_used=50, brand_match_pct=100.0,
            best_offer_share=0.0, p20=1, p25=1, p50=1, p75=1, spread_pct=1, median_buyer_shipping=0,
            net_at_p50=1, net_at_p25=1, buy_ceiling=1, headroom=1.0,
            profit_pool_week=pool if score is None else score, gate_failures=list(failures), score=score,
        )
    ranked = rank([
        ns("low", 10.0), ns("fail-big", None, ["STR"], pool=99.0), ns("high", 50.0),
        ns("fail-small", None, ["STR"], pool=1.0),
    ])
    assert [s.name for s in ranked] == ["high", "low", "fail-big", "fail-small"]


def test_candidate_flagged_below_ceiling():
    stats = _stats()
    cards = [_card("cheap", stats.buy_ceiling - 20), _card("pricey", stats.buy_ceiling + 1)]
    cands = find_candidates(_seed(), stats, cards, NO_TAX)
    assert [c.item_id for c in cands] == ["cheap"]
    assert cands[0].action == "buy"
    assert cands[0].profit_at_p50 == pytest.approx(stats.net_at_p50 - (stats.buy_ceiling - 20), abs=0.01)
    assert cands[0].profit_at_p25 < cands[0].profit_at_p50


def test_candidate_counts_shipping_against_ceiling():
    stats = _stats()
    cards = [_card("ship", stats.buy_ceiling - 5, shipping=10.0)]
    assert find_candidates(_seed(), stats, cards, NO_TAX) == []


def test_candidate_drops_lots_and_parts():
    stats = _stats()
    cards = [
        _card("lot", 50.0, title="Alden Indy boots lot of 2"),
        _card("parts", 50.0, title="Alden Indy for parts repair"),
        _card("offbrand", 50.0, title="Indy style boot"),
    ]
    assert find_candidates(_seed(), stats, cards, NO_TAX) == []


def test_auction_candidate_marked_watch():
    stats = _stats()
    cards = [
        _card("soon", 50.0, auction=True, time_left="3h 12m left"),
        _card("later", 50.0, auction=True, time_left="4d 2h left"),
    ]
    cands = find_candidates(_seed(), stats, cards, NO_TAX)
    assert [c.item_id for c in cands] == ["soon"]
    assert cands[0].action == "watch"


def test_parse_time_left_hours():
    assert parse_time_left_hours("1d 3h left") == 27.0
    assert parse_time_left_hours("45m left") == 0.75
    assert parse_time_left_hours(None) is None
    assert parse_time_left_hours("Buy It Now") is None


def test_screen_niche_with_stubbed_fetch(monkeypatch):
    import ebay_tracker.screener as screener

    seen = []

    def fetch(url):
        seen.append(url)
        return "sold" if "LH_Sold" in url else "active"

    monkeypatch.setattr(screener, "parse_listings", lambda html, search_id: _sold([300.0] * 30))
    monkeypatch.setattr(screener, "parse_active_cards", lambda html: [])
    monkeypatch.setattr(screener, "parse_result_count", lambda html: 60 if html == "sold" else 40)
    stats = screen_niche(_seed(), fetch, NO_TAX, THRESHOLDS, Gates())
    assert len(seen) == 2
    assert "LH_ItemCondition=3000" in seen[0] and "LH_ItemCondition=3000" in seen[1]
    assert stats.str_pct == 60.0


def test_scan_listings_dedupes_and_matches_misspellings(monkeypatch):
    import ebay_tracker.screener as screener

    stats = _stats()
    seed = _seed(alt_queries=["Aldenn Indy"])
    pages = {
        "Alden": [_card("1", 100.0), _card("2", 120.0)],
        "Aldenn": [_card("1", 100.0), _card("3", 90.0, title="Aldenn Indy boots 11")],
    }

    def fetch(url):
        return "Aldenn" if "Aldenn" in url else "Alden"

    monkeypatch.setattr(screener, "parse_active_cards", lambda html: pages[html])
    cands = scan_listings(seed, stats, fetch, NO_TAX)
    assert sorted(c.item_id for c in cands) == ["1", "2", "3"]
    assert next(c for c in cands if c.item_id == "3").source_query == "Aldenn Indy"


def test_menswear_seed_file_loads():
    seeds = load_seeds("seeds/menswear.toml")
    assert len(seeds) >= 40
    assert all(s.brand and s.ship_cost > 0 for s in seeds)
    assert len({s.name for s in seeds}) == len(seeds)
    assert any(s.athletic_shoes for s in seeds)
