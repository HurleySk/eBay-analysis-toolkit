import pandas as pd

from ebay_tracker.config import FeeConfig, ThresholdConfig
from ebay_tracker.fees import eBayFeeCalculator
from ebay_tracker.models import ActiveListing, Listing, ProfitAnalysis
from ebay_tracker.prediction import TimeToSellPredictor


def run_profit_analysis(
    listing: ActiveListing,
    comps: list[Listing],
    fee_config: FeeConfig,
    threshold_config: ThresholdConfig,
) -> ProfitAnalysis:
    calculator = eBayFeeCalculator(
        final_value_pct=fee_config.final_value_pct,
        payment_processing_pct=fee_config.payment_processing_pct,
        payment_processing_flat=fee_config.payment_processing_flat,
        shipping_cost=fee_config.shipping_cost,
        sales_tax_rate=fee_config.sales_tax_rate,
    )

    purchase_tax = calculator.calculate_purchase_tax(listing.price)
    total_purchase_cost = listing.price + (listing.shipping or 0) + purchase_tax

    if not comps:
        zero_net = calculator.calculate_net_proceeds(0)
        return ProfitAnalysis(
            purchase_price=listing.price,
            purchase_shipping=listing.shipping or 0,
            purchase_tax=purchase_tax,
            total_purchase_cost=total_purchase_cost,
            expected_sale_price=0,
            sale_price_25th=0,
            sale_price_75th=0,
            net_proceeds=zero_net,
            projected_profit=-total_purchase_cost,
            projected_profit_pct=-100.0,
            meets_threshold=False,
            threshold_detail="No comparable sales data",
            time_to_sell=None,
            confidence="none",
            comp_count=0,
            comps=[],
        )

    prices = pd.Series([c.price for c in comps])
    expected_sale_price = float(prices.median())
    sale_price_25th = float(prices.quantile(0.25))
    sale_price_75th = float(prices.quantile(0.75))

    comp_shipping = [c.shipping for c in comps if c.shipping is not None]
    median_buyer_shipping = float(pd.Series(comp_shipping).median()) if comp_shipping else 0.0

    net_proceeds = calculator.calculate_net_proceeds(expected_sale_price, median_buyer_shipping)
    projected_profit = net_proceeds.net - total_purchase_cost
    projected_profit_pct = (projected_profit / total_purchase_cost * 100) if total_purchase_cost > 0 else 0.0
    projected_profit_pct = round(projected_profit_pct, 2)

    meets_threshold = threshold_config.check(projected_profit_pct, projected_profit)
    threshold_detail = threshold_config.explain(projected_profit_pct, projected_profit)

    predictor = TimeToSellPredictor(comps)
    time_to_sell = predictor.predict(expected_sale_price)

    comp_count = len(comps)
    if comp_count >= 20:
        confidence = "high"
    elif comp_count >= 10:
        confidence = "medium"
    elif comp_count >= 1:
        confidence = "low"
    else:
        confidence = "none"

    return ProfitAnalysis(
        purchase_price=listing.price,
        purchase_shipping=listing.shipping or 0,
        purchase_tax=purchase_tax,
        total_purchase_cost=total_purchase_cost,
        expected_sale_price=expected_sale_price,
        sale_price_25th=sale_price_25th,
        sale_price_75th=sale_price_75th,
        net_proceeds=net_proceeds,
        projected_profit=round(projected_profit, 2),
        projected_profit_pct=projected_profit_pct,
        meets_threshold=meets_threshold,
        threshold_detail=threshold_detail,
        time_to_sell=time_to_sell,
        confidence=confidence,
        comp_count=comp_count,
        comps=comps,
    )
