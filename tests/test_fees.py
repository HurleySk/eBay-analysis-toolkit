import pytest
from ebay_tracker.fees import eBayFeeCalculator


@pytest.fixture
def default_calculator():
    return eBayFeeCalculator()


@pytest.fixture
def no_tax_calculator():
    return eBayFeeCalculator(buyer_tax_rate=0.0)


@pytest.fixture
def custom_calculator():
    return eBayFeeCalculator(
        final_value_pct=12.35,
        payment_processing_pct=2.35,
        payment_processing_flat=0.30,
        shipping_cost=8.50,
        sales_tax_rate=7.0,
        buyer_tax_rate=0.0,
    )


def test_default_fee_rates(default_calculator):
    assert default_calculator.final_value_pct == 13.6
    assert default_calculator.payment_processing_pct == 0.0
    assert default_calculator.payment_processing_flat == 0.40
    assert default_calculator.shipping_cost == 0.00
    assert default_calculator.sales_tax_rate == 0.00
    assert default_calculator.buyer_tax_rate == 7.0
    assert default_calculator.athletic_shoes is False


def test_fvf_includes_payment_processing(no_tax_calculator):
    # Managed payments: no separate % processing fee, just FVF + per-order fee
    result = no_tax_calculator.calculate_net_proceeds(100.00)
    assert result.final_value_fee == pytest.approx(13.60, abs=0.01)
    assert result.payment_processing_fee == pytest.approx(0.40, abs=0.01)
    assert result.net == pytest.approx(100.00 - 13.60 - 0.40, abs=0.01)


def test_fvf_charged_on_buyer_sales_tax(default_calculator):
    result = default_calculator.calculate_net_proceeds(100.00)
    assert result.gross == 100.00
    assert result.final_value_fee == pytest.approx(107.00 * 0.136, abs=0.01)
    assert result.net == pytest.approx(100.00 - 107.00 * 0.136 - 0.40, abs=0.01)


def test_sneaker_fee_profile_over_150():
    calc = eBayFeeCalculator(athletic_shoes=True, buyer_tax_rate=0.0)
    result = calc.calculate_net_proceeds(200.00)
    assert result.final_value_fee == pytest.approx(16.00, abs=0.01)
    assert result.payment_processing_fee == 0.0
    assert result.net == pytest.approx(184.00, abs=0.01)


def test_sneaker_fee_profile_under_150_uses_standard_rate():
    calc = eBayFeeCalculator(athletic_shoes=True, buyer_tax_rate=0.0)
    result = calc.calculate_net_proceeds(100.00)
    assert result.final_value_fee == pytest.approx(13.60, abs=0.01)
    assert result.payment_processing_fee == pytest.approx(0.40, abs=0.01)


def test_sneaker_threshold_counts_shipping_and_tax():
    # $140 + $5 shipping = $145, plus 7% tax = $155.15 total sale -> 8% tier
    calc = eBayFeeCalculator(athletic_shoes=True)
    result = calc.calculate_net_proceeds(140.00, shipping_to_buyer=5.00)
    assert result.final_value_fee == pytest.approx(145.00 * 1.07 * 0.08, abs=0.01)
    assert result.payment_processing_fee == 0.0


def test_net_proceeds_with_seller_shipping(custom_calculator):
    result = custom_calculator.calculate_net_proceeds(50.00)
    assert result.shipping_cost == 8.50
    assert result.gross == 50.00
    expected_fvf = 50.00 * 12.35 / 100
    expected_pp = 50.00 * 2.35 / 100 + 0.30
    expected_net = 50.00 - expected_fvf - expected_pp - 8.50
    assert result.net == pytest.approx(expected_net, abs=0.01)


def test_net_proceeds_total_fees(default_calculator):
    result = default_calculator.calculate_net_proceeds(100.00)
    assert result.total_fees == pytest.approx(
        result.final_value_fee + result.payment_processing_fee + result.shipping_cost,
        abs=0.01,
    )


def test_calculate_purchase_tax(custom_calculator):
    tax = custom_calculator.calculate_purchase_tax(100.00)
    assert tax == pytest.approx(7.00, abs=0.01)


def test_calculate_purchase_tax_zero_rate(default_calculator):
    tax = default_calculator.calculate_purchase_tax(100.00)
    assert tax == 0.00


def test_zero_sale_price(default_calculator):
    result = default_calculator.calculate_net_proceeds(0.00)
    assert result.gross == 0.00
    assert result.final_value_fee == 0.00
    assert result.payment_processing_fee == pytest.approx(0.40, abs=0.01)
    assert result.net == pytest.approx(-0.40, abs=0.01)


def test_high_value_item(no_tax_calculator):
    result = no_tax_calculator.calculate_net_proceeds(500.00)
    expected_net = 500.00 - 500.00 * 0.136 - 0.40
    assert result.net == pytest.approx(expected_net, abs=0.01)


def test_net_proceeds_with_buyer_shipping(no_tax_calculator):
    result = no_tax_calculator.calculate_net_proceeds(40.00, shipping_to_buyer=7.00)
    assert result.gross == 47.00
    assert result.final_value_fee == pytest.approx(47.00 * 0.136, abs=0.01)
    assert result.payment_processing_fee == pytest.approx(0.40, abs=0.01)
