from ebay_tracker.models import NetProceeds


class eBayFeeCalculator:
    def __init__(
        self,
        final_value_pct: float = 13.25,
        payment_processing_pct: float = 2.35,
        payment_processing_flat: float = 0.30,
        shipping_cost: float = 0.00,
        sales_tax_rate: float = 0.00,
    ):
        self.final_value_pct = final_value_pct
        self.payment_processing_pct = payment_processing_pct
        self.payment_processing_flat = payment_processing_flat
        self.shipping_cost = shipping_cost
        self.sales_tax_rate = sales_tax_rate

    def calculate_net_proceeds(self, sale_price: float) -> NetProceeds:
        gross = sale_price
        final_value_fee = gross * self.final_value_pct / 100
        payment_processing_fee = gross * self.payment_processing_pct / 100 + self.payment_processing_flat
        total_fees = final_value_fee + payment_processing_fee + self.shipping_cost
        net = gross - total_fees

        return NetProceeds(
            gross=gross,
            final_value_fee=round(final_value_fee, 2),
            payment_processing_fee=round(payment_processing_fee, 2),
            shipping_cost=self.shipping_cost,
            total_fees=round(total_fees, 2),
            net=round(net, 2),
        )

    def calculate_purchase_tax(self, purchase_price: float) -> float:
        return round(purchase_price * self.sales_tax_rate / 100, 2)
