from ebay_tracker.models import NetProceeds

# eBay US seller fees, "Most categories" (incl. Clothing, Shoes & Accessories):
# https://www.ebay.com/help/selling/fees-credits-invoices/selling-fees?id=4822
# Payment processing is included in the final value fee (managed payments), and
# the fee is charged on the total sale: item + shipping + the sales tax eBay collects.
DEFAULT_FINAL_VALUE_PCT = 13.6
DEFAULT_PER_ORDER_FEE = 0.40
# Approximate US average combined sales tax; only used to size the FVF base.
DEFAULT_BUYER_TAX_RATE = 7.0

# Men's/Women's Athletic Shoes: 8% and no per-order fee when the total sale is $150+.
ATHLETIC_SHOES_THRESHOLD = 150.0
ATHLETIC_SHOES_PCT = 8.0


class eBayFeeCalculator:
    def __init__(
        self,
        final_value_pct: float = DEFAULT_FINAL_VALUE_PCT,
        payment_processing_pct: float = 0.0,
        payment_processing_flat: float = DEFAULT_PER_ORDER_FEE,
        shipping_cost: float = 0.00,
        sales_tax_rate: float = 0.00,
        buyer_tax_rate: float = DEFAULT_BUYER_TAX_RATE,
        athletic_shoes: bool = False,
    ):
        self.final_value_pct = final_value_pct
        self.payment_processing_pct = payment_processing_pct
        self.payment_processing_flat = payment_processing_flat
        self.shipping_cost = shipping_cost
        self.sales_tax_rate = sales_tax_rate
        self.buyer_tax_rate = buyer_tax_rate
        self.athletic_shoes = athletic_shoes

    def calculate_net_proceeds(self, sale_price: float, shipping_to_buyer: float = 0.0) -> NetProceeds:
        gross = sale_price + shipping_to_buyer
        fee_base = gross * (1 + self.buyer_tax_rate / 100)

        fvf_pct = self.final_value_pct
        per_order_fee = self.payment_processing_flat
        if self.athletic_shoes and fee_base >= ATHLETIC_SHOES_THRESHOLD:
            fvf_pct = ATHLETIC_SHOES_PCT
            per_order_fee = 0.0

        final_value_fee = fee_base * fvf_pct / 100
        payment_processing_fee = gross * self.payment_processing_pct / 100 + per_order_fee
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
