import pytest
from ebay_tracker.fees import eBayFeeCalculator


@pytest.fixture
def default_calculator():
    return eBayFeeCalculator()


@pytest.fixture
def custom_calculator():
    return eBayFeeCalculator(
        final_value_pct=12.35,
        payment_processing_pct=2.35,
        payment_processing_flat=0.30,
        shipping_cost=8.50,
        sales_tax_rate=7.0,
    )


def test_default_fee_rates(default_calculator):
    assert default_calculator.final_value_pct == 13.25
    assert default_calculator.payment_processing_pct == 2.35
    assert default_calculator.payment_processing_flat == 0.30
    assert default_calculator.shipping_cost == 0.00
    assert default_calculator.sales_tax_rate == 0.00


def test_net_proceeds_no_shipping(default_calculator):
    result = default_calculator.calculate_net_proceeds(50.00)
    assert result.gross == 50.00
    assert result.final_value_fee == pytest.approx(6.625, abs=0.01)
    assert result.payment_processing_fee == pytest.approx(1.475, abs=0.01)
    assert result.shipping_cost == 0.00
    assert result.net == pytest.approx(50.00 - 6.625 - 1.475, abs=0.01)


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
    assert result.payment_processing_fee == pytest.approx(0.30, abs=0.01)
    assert result.net == pytest.approx(-0.30, abs=0.01)


def test_high_value_item(default_calculator):
    result = default_calculator.calculate_net_proceeds(500.00)
    expected_fvf = 500.00 * 13.25 / 100
    expected_pp = 500.00 * 2.35 / 100 + 0.30
    expected_net = 500.00 - expected_fvf - expected_pp
    assert result.net == pytest.approx(expected_net, abs=0.01)
