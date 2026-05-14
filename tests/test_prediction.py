import pytest
from datetime import date
from ebay_tracker.models import Listing
from ebay_tracker.prediction import TimeToSellPredictor


def _make_listing(sold_date: date, price: float = 40.0) -> Listing:
    return Listing(
        id=None, search_id=1, ebay_item_id="x",
        title="Test", price=price, shipping=0.0,
        condition="Pre-owned", sold_date=sold_date,
        url=None, created_at=None,
    )


@pytest.fixture
def many_comps():
    base = date(2025, 1, 1)
    listings = []
    for i in range(25):
        d = date.fromordinal(base.toordinal() + i * 2)
        price = 30.0 + (i % 5) * 5
        listings.append(_make_listing(d, price))
    return listings


@pytest.fixture
def few_comps():
    return [
        _make_listing(date(2025, 1, 1), 30.0),
        _make_listing(date(2025, 1, 10), 40.0),
        _make_listing(date(2025, 1, 20), 35.0),
    ]


def test_predict_high_confidence(many_comps):
    predictor = TimeToSellPredictor(many_comps)
    pred = predictor.predict(target_price=35.0)
    assert pred is not None
    assert pred.confidence == "high"
    assert pred.sample_size == 25
    assert pred.median_days > 0
    assert pred.fast_days <= pred.median_days
    assert pred.median_days <= pred.slow_days
    assert pred.slow_days <= pred.ninety_pct_days


def test_predict_price_tier_below_median(many_comps):
    predictor = TimeToSellPredictor(many_comps)
    pred = predictor.predict(target_price=30.0)
    assert pred is not None
    assert pred.price_tier == "below_median"


def test_predict_price_tier_above_median(many_comps):
    predictor = TimeToSellPredictor(many_comps)
    pred = predictor.predict(target_price=50.0)
    assert pred is not None
    assert pred.price_tier == "above_median"


def test_predict_below_median_faster_than_above(many_comps):
    predictor = TimeToSellPredictor(many_comps)
    low = predictor.predict(target_price=30.0)
    high = predictor.predict(target_price=50.0)
    assert low is not None and high is not None
    assert low.median_days <= high.median_days


def test_predict_low_comp_count_fallback(few_comps):
    predictor = TimeToSellPredictor(few_comps)
    pred = predictor.predict(target_price=35.0)
    assert pred is not None
    assert pred.confidence == "low"
    assert pred.sample_size == 3


def test_predict_no_comps():
    predictor = TimeToSellPredictor([])
    pred = predictor.predict(target_price=35.0)
    assert pred is None


def test_predict_no_dated_comps():
    comps = [
        Listing(None, 1, "x", "T", 40.0, 0.0, None, None, None, None),
        Listing(None, 1, "y", "T", 45.0, 0.0, None, None, None, None),
    ]
    predictor = TimeToSellPredictor(comps)
    pred = predictor.predict(target_price=40.0)
    assert pred is None


def test_predict_medium_confidence():
    base = date(2025, 1, 1)
    comps = [_make_listing(date.fromordinal(base.toordinal() + i * 3), 40.0) for i in range(15)]
    predictor = TimeToSellPredictor(comps)
    pred = predictor.predict(target_price=40.0)
    assert pred is not None
    assert pred.confidence == "medium"


def test_predict_at_median(many_comps):
    predictor = TimeToSellPredictor(many_comps)
    prices = sorted([c.price for c in many_comps])
    median_price = prices[len(prices) // 2]
    pred = predictor.predict(target_price=median_price)
    assert pred is not None
    assert pred.price_tier == "at_median"
