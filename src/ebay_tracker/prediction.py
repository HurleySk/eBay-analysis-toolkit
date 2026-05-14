import numpy as np
from scipy import stats

from ebay_tracker.models import Listing, SellTimePrediction


class TimeToSellPredictor:
    def __init__(self, comps: list[Listing]):
        self.comps = comps
        self._dated = sorted(
            [c for c in comps if c.sold_date is not None],
            key=lambda c: c.sold_date,
        )

    def predict(self, target_price: float) -> SellTimePrediction | None:
        if len(self._dated) < 2:
            return None

        intervals = self._compute_intervals()
        if not intervals:
            return None

        price_tier = self._classify_price_tier(target_price)
        sample_size = len(self._dated)
        confidence = self._assess_confidence(sample_size)

        if sample_size >= 5:
            prediction = self._fit_lognormal(intervals, price_tier)
        else:
            prediction = self._fallback_estimate(intervals, price_tier)

        if prediction is None:
            return None

        prediction.confidence = confidence
        prediction.sample_size = sample_size
        prediction.price_tier = price_tier
        return prediction

    def _compute_intervals(self) -> list[float]:
        intervals = []
        for i in range(1, len(self._dated)):
            days = (self._dated[i].sold_date - self._dated[i - 1].sold_date).days
            if days > 0:
                intervals.append(float(days))
        return intervals

    def _classify_price_tier(self, target_price: float) -> str:
        prices = sorted([c.price for c in self._dated])
        median_price = float(np.median(prices))
        tolerance = median_price * 0.05
        if target_price < median_price - tolerance:
            return "below_median"
        elif target_price > median_price + tolerance:
            return "above_median"
        return "at_median"

    def _assess_confidence(self, sample_size: int) -> str:
        if sample_size >= 20:
            return "high"
        if sample_size >= 10:
            return "medium"
        return "low"

    def _fit_lognormal(self, intervals: list[float], price_tier: str) -> SellTimePrediction | None:
        arr = np.array(intervals)
        try:
            shape, loc, scale = stats.lognorm.fit(arr, floc=0)
        except Exception:
            return self._fallback_estimate(intervals, price_tier)

        adjustment = self._price_adjustment(price_tier)
        dist = stats.lognorm(shape, loc=0, scale=scale * adjustment)

        return SellTimePrediction(
            median_days=round(float(dist.ppf(0.50)), 1),
            fast_days=round(float(dist.ppf(0.25)), 1),
            slow_days=round(float(dist.ppf(0.75)), 1),
            ninety_pct_days=round(float(dist.ppf(0.90)), 1),
            confidence="",
            sample_size=0,
            price_tier="",
        )

    def _fallback_estimate(self, intervals: list[float], price_tier: str) -> SellTimePrediction:
        avg_interval = float(np.mean(intervals))
        adjustment = self._price_adjustment(price_tier)
        base = avg_interval * adjustment
        return SellTimePrediction(
            median_days=round(base, 1),
            fast_days=round(base * 0.5, 1),
            slow_days=round(base * 1.5, 1),
            ninety_pct_days=round(base * 2.5, 1),
            confidence="",
            sample_size=0,
            price_tier="",
        )

    def _price_adjustment(self, price_tier: str) -> float:
        if price_tier == "below_median":
            return 0.75
        elif price_tier == "above_median":
            return 1.35
        return 1.0
