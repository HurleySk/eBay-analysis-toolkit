import pytest
from datetime import date

from ebay_tracker.models import ActiveListing, Listing
from ebay_tracker.config import FeeConfig, ThresholdConfig
from ebay_tracker.evaluator import run_profit_analysis


def _make_active_listing(price: float = 25.00, shipping: float = 5.99) -> ActiveListing:
    return ActiveListing(
        item_id="123456", title="Levi's 501 Jeans 32x30",
        price=price, shipping=shipping, condition="Pre-owned",
        category_id=11483, item_specifics={"Brand": "Levi's"},
        url="https://www.ebay.com/itm/123456", seller="seller1",
    )


def _make_comps(prices: list[float], base_date: date = date(2025, 1, 1)) -> list[Listing]:
    comps = []
    for i, price in enumerate(prices):
        d = date.fromordinal(base_date.toordinal() + i * 3)
        comps.append(Listing(
            id=i, search_id=1, ebay_item_id=f"comp{i}",
            title=f"Comp {i}", price=price, shipping=0.0,
            condition="Pre-owned", sold_date=d, url=None, created_at=None,
        ))
    return comps


def test_profitable_analysis():
    listing = _make_active_listing(price=15.00, shipping=3.00)
    comps = _make_comps([45.0, 50.0, 55.0, 48.0, 52.0, 47.0, 51.0, 49.0, 53.0, 46.0])
    fee_config = FeeConfig()
    threshold_config = ThresholdConfig(min_profit_pct=20.0, min_profit_dollar=5.0, mode="and")

    result = run_profit_analysis(listing, comps, fee_config, threshold_config)

    assert result.total_purchase_cost == 18.00
    assert result.expected_sale_price > 0
    assert result.projected_profit > 0
    assert result.projected_profit_pct > 0
    assert result.meets_threshold is True
    assert result.comp_count == 10
    assert result.confidence == "medium"


def test_unprofitable_analysis():
    listing = _make_active_listing(price=55.00, shipping=5.00)
    comps = _make_comps([30.0, 35.0, 32.0, 28.0, 33.0])
    fee_config = FeeConfig()
    threshold_config = ThresholdConfig(min_profit_pct=20.0, min_profit_dollar=10.0, mode="and")

    result = run_profit_analysis(listing, comps, fee_config, threshold_config)

    assert result.projected_profit < 0
    assert result.meets_threshold is False
    assert "FAIL" in result.threshold_detail


def test_analysis_with_sales_tax():
    listing = _make_active_listing(price=20.00, shipping=5.00)
    comps = _make_comps([50.0, 55.0, 48.0, 52.0, 51.0])
    fee_config = FeeConfig(sales_tax_rate=8.25)
    threshold_config = ThresholdConfig()

    result = run_profit_analysis(listing, comps, fee_config, threshold_config)

    expected_tax = round(20.00 * 8.25 / 100, 2)
    assert result.purchase_tax == expected_tax
    assert result.total_purchase_cost == pytest.approx(20.00 + 5.00 + expected_tax, abs=0.01)


def test_analysis_with_seller_shipping():
    listing = _make_active_listing(price=20.00, shipping=5.00)
    comps = _make_comps([50.0, 55.0, 48.0, 52.0, 51.0])
    fee_config = FeeConfig(shipping_cost=7.50)
    threshold_config = ThresholdConfig()

    result = run_profit_analysis(listing, comps, fee_config, threshold_config)

    assert result.net_proceeds.shipping_cost == 7.50


def test_analysis_empty_comps():
    listing = _make_active_listing()
    fee_config = FeeConfig()
    threshold_config = ThresholdConfig()

    result = run_profit_analysis(listing, [], fee_config, threshold_config)

    assert result.comp_count == 0
    assert result.confidence == "none"
    assert result.meets_threshold is False
    assert result.time_to_sell is None


def test_analysis_includes_time_to_sell():
    listing = _make_active_listing(price=20.00, shipping=5.00)
    comps = _make_comps([40.0 + i for i in range(25)])
    fee_config = FeeConfig()
    threshold_config = ThresholdConfig()

    result = run_profit_analysis(listing, comps, fee_config, threshold_config)

    assert result.time_to_sell is not None
    assert result.time_to_sell.median_days > 0


def test_analysis_threshold_or_mode():
    listing = _make_active_listing(price=10.00, shipping=0.00)
    comps = _make_comps([15.0, 16.0, 14.0, 15.5, 14.5])
    fee_config = FeeConfig()
    threshold_config = ThresholdConfig(min_profit_pct=10.0, min_profit_dollar=50.0, mode="or")

    result = run_profit_analysis(listing, comps, fee_config, threshold_config)

    assert result.projected_profit_pct > 10.0
    assert result.projected_profit < 50.0
    assert result.meets_threshold is True
