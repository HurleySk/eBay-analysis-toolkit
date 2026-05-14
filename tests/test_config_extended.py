import json
import pytest
from ebay_tracker.config import (
    FeeConfig, ThresholdConfig, UserPreferences,
    get_user_prefs, save_user_prefs,
)


def test_fee_config_defaults():
    fc = FeeConfig()
    assert fc.final_value_pct == 13.25
    assert fc.payment_processing_pct == 2.35
    assert fc.payment_processing_flat == 0.30
    assert fc.shipping_cost == 0.00
    assert fc.sales_tax_rate == 0.00
    assert fc.state is None


def test_threshold_config_defaults():
    tc = ThresholdConfig()
    assert tc.min_profit_pct == 20.0
    assert tc.min_profit_dollar == 10.0
    assert tc.mode == "and"


def test_threshold_config_and_mode():
    tc = ThresholdConfig(min_profit_pct=15.0, min_profit_dollar=5.0, mode="and")
    assert tc.check(profit_pct=20.0, profit_dollar=8.0) is True
    assert tc.check(profit_pct=20.0, profit_dollar=3.0) is False
    assert tc.check(profit_pct=10.0, profit_dollar=8.0) is False
    assert tc.check(profit_pct=10.0, profit_dollar=3.0) is False


def test_threshold_config_or_mode():
    tc = ThresholdConfig(min_profit_pct=15.0, min_profit_dollar=5.0, mode="or")
    assert tc.check(profit_pct=20.0, profit_dollar=8.0) is True
    assert tc.check(profit_pct=20.0, profit_dollar=3.0) is True
    assert tc.check(profit_pct=10.0, profit_dollar=8.0) is True
    assert tc.check(profit_pct=10.0, profit_dollar=3.0) is False


def test_threshold_config_explain_and():
    tc = ThresholdConfig(min_profit_pct=20.0, min_profit_dollar=10.0, mode="and")
    detail = tc.explain(profit_pct=13.6, profit_dollar=4.52)
    assert "FAIL" in detail
    assert "20.0%" in detail
    assert "$10.00" in detail


def test_threshold_config_explain_or_pass():
    tc = ThresholdConfig(min_profit_pct=20.0, min_profit_dollar=10.0, mode="or")
    detail = tc.explain(profit_pct=25.0, profit_dollar=4.52)
    assert "PASS" in detail


def test_user_prefs_with_fees_and_thresholds(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr("ebay_tracker.config.get_prefs_path", lambda: config_path)

    prefs = UserPreferences(
        gender_preference="mens",
        favorite_categories=[11483],
        fees=FeeConfig(shipping_cost=8.50, sales_tax_rate=7.0, state="TX"),
        thresholds=ThresholdConfig(min_profit_pct=25.0, min_profit_dollar=15.0, mode="and"),
    )
    save_user_prefs(prefs)

    loaded = get_user_prefs()
    assert loaded.fees.shipping_cost == 8.50
    assert loaded.fees.sales_tax_rate == 7.0
    assert loaded.fees.state == "TX"
    assert loaded.thresholds.min_profit_pct == 25.0
    assert loaded.thresholds.mode == "and"


def test_user_prefs_backward_compatible(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "gender_preference": "mens",
        "favorite_categories": [11483],
    }))
    monkeypatch.setattr("ebay_tracker.config.get_prefs_path", lambda: config_path)

    loaded = get_user_prefs()
    assert loaded.gender_preference == "mens"
    assert loaded.fees.final_value_pct == 13.25
    assert loaded.thresholds.min_profit_pct == 20.0
