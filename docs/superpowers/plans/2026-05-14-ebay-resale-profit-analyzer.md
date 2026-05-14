# eBay Resale Profit Analyzer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add profit analysis for eBay resale — evaluate active listings against sold comps, calculate profit after fees, predict time-to-sell, expose via CLI + MCP server + Claude Code plugin.

**Architecture:** Single-repo enhancement. New modules (`fees.py`, `evaluator.py`, `prediction.py`, `server.py`) sit alongside existing code in `src/ebay_tracker/`. The MCP server and CLI both call the same core logic. Plugin config at repo root.

**Tech Stack:** Python 3.11+, typer, httpx, BeautifulSoup, pandas, numpy, scipy (log-normal), mcp SDK (FastMCP), Rich (CLI output)

**Spec:** `docs/superpowers/specs/2026-05-14-ebay-resale-profit-analyzer-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `pyproject.toml` | Add scipy, mcp dependencies |
| Modify | `src/ebay_tracker/models.py` | Add ActiveListing, SuggestedQuery, NetProceeds, SellTimePrediction, ProfitAnalysis |
| Create | `src/ebay_tracker/fees.py` | eBayFeeCalculator, fee math |
| Modify | `src/ebay_tracker/config.py` | FeeConfig, ThresholdConfig, extend UserPreferences + save/load |
| Modify | `src/ebay_tracker/scraper.py` | fetch_active_listing, parse_active_listing, extract_search_query |
| Create | `src/ebay_tracker/prediction.py` | TimeToSellPredictor, log-normal fitting |
| Create | `src/ebay_tracker/evaluator.py` | Orchestrates full profit analysis |
| Modify | `src/ebay_tracker/cli.py` | Add `evaluate` command, fix missing rate_limit_delay import |
| Create | `src/ebay_tracker/server.py` | MCP server with 5 tools |
| Create | `tests/test_fees.py` | Fee calculator tests |
| Create | `tests/test_prediction.py` | Time-to-sell prediction tests |
| Create | `tests/test_evaluator.py` | Evaluator integration tests |
| Create | `tests/fixtures/ebay_active_listing.html` | HTML fixture for active listing parser |
| Create | `.claude-plugin/plugin.json` | Plugin manifest |
| Create | `.mcp.json` | MCP server registration |
| Create | `skills/evaluate/SKILL.md` | Agent workflow skill |
| Create | `.github/workflows/version-bump.yml` | Marketplace sync CI |

---

### Task 1: Add Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add scipy and mcp to dependencies**

In `pyproject.toml`, add to the `dependencies` list:

```toml
[project]
name = "ebay-tracker"
version = "0.1.0"
description = "CLI tool to track eBay sold listings and predict prices"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.9.0",
    "httpx>=0.27.0",
    "beautifulsoup4>=4.12.0",
    "lxml>=5.0.0",
    "pandas>=2.0.0",
    "rich>=13.0.0",
    "python-dotenv>=1.0.0",
    "scipy>=1.11.0",
    "mcp>=1.0.0",
]
```

- [ ] **Step 2: Install updated dependencies**

Run: `uv sync`
Expected: All dependencies install successfully including scipy and mcp.

- [ ] **Step 3: Verify imports work**

Run: `uv run python -c "import scipy.stats; from mcp.server.fastmcp import FastMCP; print('OK')"`
Expected: Prints `OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add scipy and mcp dependencies for profit analysis"
```

---

### Task 2: New Data Models

**Files:**
- Modify: `src/ebay_tracker/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write tests for new models**

Add to `tests/test_models.py`:

```python
from datetime import date
from ebay_tracker.models import (
    ActiveListing, SuggestedQuery, NetProceeds,
    SellTimePrediction, ProfitAnalysis, Listing,
)


def test_active_listing_creation():
    listing = ActiveListing(
        item_id="123456",
        title="Levi's 501 Jeans 32x30",
        price=25.00,
        shipping=5.99,
        condition="Pre-owned",
        category_id=11483,
        item_specifics={"Brand": "Levi's", "Size": "32x30"},
        url="https://www.ebay.com/itm/123456",
        seller="seller123",
    )
    assert listing.item_id == "123456"
    assert listing.price == 25.00
    assert listing.item_specifics["Brand"] == "Levi's"


def test_active_listing_total_cost():
    listing = ActiveListing(
        item_id="123456",
        title="Test",
        price=25.00,
        shipping=5.99,
        condition=None,
        category_id=None,
        item_specifics={},
        url="https://www.ebay.com/itm/123456",
        seller=None,
    )
    assert listing.total_cost == 30.99


def test_active_listing_total_cost_no_shipping():
    listing = ActiveListing(
        item_id="123456",
        title="Test",
        price=25.00,
        shipping=None,
        condition=None,
        category_id=None,
        item_specifics={},
        url="https://www.ebay.com/itm/123456",
        seller=None,
    )
    assert listing.total_cost == 25.00


def test_suggested_query_creation():
    sq = SuggestedQuery(
        query="Levi's 501 jeans 32x30",
        filters={"condition": "Pre-owned", "category": 11483},
        raw_attributes={"Brand": "Levi's", "Size": "32x30"},
    )
    assert sq.query == "Levi's 501 jeans 32x30"
    assert sq.filters["category"] == 11483


def test_net_proceeds_creation():
    np_result = NetProceeds(
        gross=50.00,
        final_value_fee=6.625,
        payment_processing_fee=1.475,
        shipping_cost=0.00,
        total_fees=8.10,
        net=41.90,
    )
    assert np_result.net == 41.90
    assert np_result.total_fees == 8.10


def test_sell_time_prediction_creation():
    pred = SellTimePrediction(
        median_days=7.5,
        fast_days=3.2,
        slow_days=14.1,
        ninety_pct_days=21.0,
        confidence="high",
        sample_size=25,
        price_tier="below_median",
    )
    assert pred.median_days == 7.5
    assert pred.confidence == "high"


def test_profit_analysis_creation():
    comps = [
        Listing(1, 1, "c1", "Comp 1", 45.0, 0.0, "Pre-owned", date(2025, 1, 5), None, None),
    ]
    analysis = ProfitAnalysis(
        purchase_price=25.00,
        purchase_shipping=5.99,
        purchase_tax=2.17,
        total_purchase_cost=33.16,
        expected_sale_price=45.00,
        sale_price_25th=38.00,
        sale_price_75th=52.00,
        net_proceeds=NetProceeds(
            gross=45.00,
            final_value_fee=5.96,
            payment_processing_fee=1.36,
            shipping_cost=0.00,
            total_fees=7.32,
            net=37.68,
        ),
        projected_profit=4.52,
        projected_profit_pct=13.63,
        meets_threshold=False,
        threshold_detail="13.6% >= 20% AND $4.52 >= $10.00: FAIL (both required)",
        time_to_sell=None,
        confidence="low",
        comp_count=1,
        comps=comps,
    )
    assert analysis.projected_profit == 4.52
    assert analysis.meets_threshold is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models.py -v -k "active_listing or suggested_query or net_proceeds or sell_time or profit_analysis"`
Expected: FAIL — ImportError for the new model classes

- [ ] **Step 3: Add new dataclasses to models.py**

Add after the existing `FetchLog` class in `src/ebay_tracker/models.py`:

```python
@dataclass
class ActiveListing:
    item_id: str
    title: str
    price: float
    shipping: float | None
    condition: str | None
    category_id: int | None
    item_specifics: dict
    url: str
    seller: str | None

    @property
    def total_cost(self) -> float:
        return self.price + (self.shipping or 0)


@dataclass
class SuggestedQuery:
    query: str
    filters: dict
    raw_attributes: dict


@dataclass
class NetProceeds:
    gross: float
    final_value_fee: float
    payment_processing_fee: float
    shipping_cost: float
    total_fees: float
    net: float


@dataclass
class SellTimePrediction:
    median_days: float
    fast_days: float
    slow_days: float
    ninety_pct_days: float
    confidence: str
    sample_size: int
    price_tier: str


@dataclass
class ProfitAnalysis:
    purchase_price: float
    purchase_shipping: float
    purchase_tax: float
    total_purchase_cost: float
    expected_sale_price: float
    sale_price_25th: float
    sale_price_75th: float
    net_proceeds: NetProceeds
    projected_profit: float
    projected_profit_pct: float
    meets_threshold: bool
    threshold_detail: str
    time_to_sell: SellTimePrediction | None
    confidence: str
    comp_count: int
    comps: list["Listing"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py -v`
Expected: All tests PASS (including existing model tests)

- [ ] **Step 5: Commit**

```bash
git add src/ebay_tracker/models.py tests/test_models.py
git commit -m "feat: add data models for profit analysis"
```

---

### Task 3: Fee Calculator

**Files:**
- Create: `src/ebay_tracker/fees.py`
- Create: `tests/test_fees.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_fees.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_fees.py -v`
Expected: FAIL — ModuleNotFoundError: No module named 'ebay_tracker.fees'

- [ ] **Step 3: Implement fees.py**

Create `src/ebay_tracker/fees.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_fees.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ebay_tracker/fees.py tests/test_fees.py
git commit -m "feat: add eBay fee calculator"
```

---

### Task 4: Extend Configuration

**Files:**
- Modify: `src/ebay_tracker/config.py`
- Create: `tests/test_config_extended.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_config_extended.py`:

```python
import json
import pytest
from pathlib import Path
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config_extended.py -v`
Expected: FAIL — ImportError for FeeConfig, ThresholdConfig

- [ ] **Step 3: Implement config extensions**

Replace the full contents of `src/ebay_tracker/config.py`:

```python
import json
from dataclasses import dataclass, field
from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    proxy_url: str | None
    db_path: Path


def get_config() -> Config:
    return Config(
        proxy_url=os.environ.get("DECODO_PROXY_URL"),
        db_path=Path(os.environ.get("EBAY_TRACKER_DB_PATH", "data/ebay_tracker.db")),
    )


@dataclass
class FeeConfig:
    final_value_pct: float = 13.25
    payment_processing_pct: float = 2.35
    payment_processing_flat: float = 0.30
    shipping_cost: float = 0.00
    sales_tax_rate: float = 0.00
    state: str | None = None


@dataclass
class ThresholdConfig:
    min_profit_pct: float = 20.0
    min_profit_dollar: float = 10.0
    mode: str = "and"

    def check(self, profit_pct: float, profit_dollar: float) -> bool:
        pct_pass = profit_pct >= self.min_profit_pct
        dollar_pass = profit_dollar >= self.min_profit_dollar
        if self.mode == "or":
            return pct_pass or dollar_pass
        return pct_pass and dollar_pass

    def explain(self, profit_pct: float, profit_dollar: float) -> str:
        pct_pass = profit_pct >= self.min_profit_pct
        dollar_pass = profit_dollar >= self.min_profit_dollar
        passes = self.check(profit_pct, profit_dollar)
        op = self.mode.upper()
        verdict = "PASS" if passes else "FAIL"
        return (
            f"{profit_pct:.1f}% >= {self.min_profit_pct}% {'OK' if pct_pass else 'NO'} "
            f"{op} ${profit_dollar:.2f} >= ${self.min_profit_dollar:.2f} {'OK' if dollar_pass else 'NO'}: "
            f"{verdict}"
        )


@dataclass
class UserPreferences:
    gender_preference: str | None = None
    favorite_categories: list[int] = field(default_factory=list)
    fees: FeeConfig = field(default_factory=FeeConfig)
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)


def get_prefs_path() -> Path:
    return Path.home() / ".config" / "ebay-tracker" / "config.json"


def get_user_prefs() -> UserPreferences:
    path = get_prefs_path()
    if path.exists():
        data = json.loads(path.read_text())
        fees_data = data.get("fees", {})
        thresholds_data = data.get("thresholds", {})
        return UserPreferences(
            gender_preference=data.get("gender_preference"),
            favorite_categories=data.get("favorite_categories", []),
            fees=FeeConfig(
                final_value_pct=fees_data.get("final_value_pct", 13.25),
                payment_processing_pct=fees_data.get("payment_processing_pct", 2.35),
                payment_processing_flat=fees_data.get("payment_processing_flat", 0.30),
                shipping_cost=fees_data.get("shipping_cost", 0.00),
                sales_tax_rate=fees_data.get("sales_tax_rate", 0.00),
                state=fees_data.get("state"),
            ),
            thresholds=ThresholdConfig(
                min_profit_pct=thresholds_data.get("min_profit_pct", 20.0),
                min_profit_dollar=thresholds_data.get("min_profit_dollar", 10.0),
                mode=thresholds_data.get("mode", "and"),
            ),
        )
    return UserPreferences()


def save_user_prefs(prefs: UserPreferences) -> None:
    path = get_prefs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "gender_preference": prefs.gender_preference,
        "favorite_categories": prefs.favorite_categories,
        "fees": {
            "final_value_pct": prefs.fees.final_value_pct,
            "payment_processing_pct": prefs.fees.payment_processing_pct,
            "payment_processing_flat": prefs.fees.payment_processing_flat,
            "shipping_cost": prefs.fees.shipping_cost,
            "sales_tax_rate": prefs.fees.sales_tax_rate,
            "state": prefs.fees.state,
        },
        "thresholds": {
            "min_profit_pct": prefs.thresholds.min_profit_pct,
            "min_profit_dollar": prefs.thresholds.min_profit_dollar,
            "mode": prefs.thresholds.mode,
        },
    }, indent=2))
```

- [ ] **Step 4: Run all config tests**

Run: `uv run pytest tests/test_config_extended.py tests/test_config.py -v`
Expected: All tests PASS (new and existing)

- [ ] **Step 5: Commit**

```bash
git add src/ebay_tracker/config.py tests/test_config_extended.py
git commit -m "feat: extend config with fee and threshold settings"
```

---

### Task 5: Active Listing Scraper

**Files:**
- Modify: `src/ebay_tracker/scraper.py`
- Create: `tests/fixtures/ebay_active_listing.html`
- Create: `tests/test_scraper_active.py`

- [ ] **Step 1: Create HTML fixture for active listing page**

Create `tests/fixtures/ebay_active_listing.html`:

```html
<!DOCTYPE html>
<html>
<head><title>Levi's 501 Original Fit Men's Jeans 32x30 Dark Wash | eBay</title></head>
<body>
<div class="vim x-item-title">
  <h1 class="x-item-title__mainTitle"><span class="ux-textspans ux-textspans--BOLD">Levi's 501 Original Fit Men's Jeans 32x30 Dark Wash</span></h1>
</div>
<div class="x-price-primary">
  <span class="ux-textspans">US $24.99</span>
</div>
<div class="vim x-item-condition">
  <span class="ux-textspans">Pre-owned</span>
</div>
<div class="ux-labels-values--shipping">
  <div class="ux-labels-values__values-content">
    <span class="ux-textspans ux-textspans--BOLD">US $5.99</span>
  </div>
</div>
<div class="x-sellercard-atf__info">
  <a class="x-sellercard-atf__info__about-seller">
    <span class="ux-textspans ux-textspans--BOLD">jeans_outlet_99</span>
  </a>
</div>
<nav class="breadcrumbs">
  <ul>
    <li><a href="/b/Mens-Jeans/11483/bn_696137">Men's Jeans</a></li>
  </ul>
</nav>
<div class="x-about-this-item">
  <div class="ux-layout-section-evo">
    <dl class="ux-labels-values">
      <div class="ux-labels-values__labels-content"><span>Brand</span></div>
      <div class="ux-labels-values__values-content"><span>Levi's</span></div>
    </dl>
    <dl class="ux-labels-values">
      <div class="ux-labels-values__labels-content"><span>Style</span></div>
      <div class="ux-labels-values__values-content"><span>501</span></div>
    </dl>
    <dl class="ux-labels-values">
      <div class="ux-labels-values__labels-content"><span>Waist Size</span></div>
      <div class="ux-labels-values__values-content"><span>32</span></div>
    </dl>
    <dl class="ux-labels-values">
      <div class="ux-labels-values__labels-content"><span>Inseam</span></div>
      <div class="ux-labels-values__values-content"><span>30</span></div>
    </dl>
    <dl class="ux-labels-values">
      <div class="ux-labels-values__labels-content"><span>Color</span></div>
      <div class="ux-labels-values__values-content"><span>Blue</span></div>
    </dl>
  </div>
</div>
</body>
</html>
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_scraper_active.py`:

```python
import pytest
from pathlib import Path
from ebay_tracker.scraper import parse_active_listing, extract_search_query, normalize_item_url


@pytest.fixture
def active_listing_html():
    fixture_path = Path(__file__).parent / "fixtures" / "ebay_active_listing.html"
    return fixture_path.read_text()


def test_parse_active_listing_title(active_listing_html):
    listing = parse_active_listing(active_listing_html, "123456789")
    assert listing.title == "Levi's 501 Original Fit Men's Jeans 32x30 Dark Wash"


def test_parse_active_listing_price(active_listing_html):
    listing = parse_active_listing(active_listing_html, "123456789")
    assert listing.price == 24.99


def test_parse_active_listing_shipping(active_listing_html):
    listing = parse_active_listing(active_listing_html, "123456789")
    assert listing.shipping == 5.99


def test_parse_active_listing_condition(active_listing_html):
    listing = parse_active_listing(active_listing_html, "123456789")
    assert listing.condition == "Pre-owned"


def test_parse_active_listing_seller(active_listing_html):
    listing = parse_active_listing(active_listing_html, "123456789")
    assert listing.seller == "jeans_outlet_99"


def test_parse_active_listing_item_specifics(active_listing_html):
    listing = parse_active_listing(active_listing_html, "123456789")
    assert listing.item_specifics["Brand"] == "Levi's"
    assert listing.item_specifics["Style"] == "501"
    assert listing.item_specifics["Waist Size"] == "32"
    assert listing.item_specifics["Inseam"] == "30"
    assert listing.item_specifics["Color"] == "Blue"


def test_parse_active_listing_item_id(active_listing_html):
    listing = parse_active_listing(active_listing_html, "123456789")
    assert listing.item_id == "123456789"


def test_extract_search_query_from_listing(active_listing_html):
    listing = parse_active_listing(active_listing_html, "123456789")
    suggested = extract_search_query(listing)
    assert "Levi's" in suggested.query or "levi" in suggested.query.lower()
    assert "501" in suggested.query
    assert suggested.raw_attributes["Brand"] == "Levi's"


def test_extract_search_query_filters(active_listing_html):
    listing = parse_active_listing(active_listing_html, "123456789")
    suggested = extract_search_query(listing)
    assert suggested.filters.get("condition") == "Pre-owned"


def test_normalize_item_url_full_url():
    url, item_id = normalize_item_url("https://www.ebay.com/itm/123456789")
    assert item_id == "123456789"
    assert "ebay.com/itm/123456789" in url


def test_normalize_item_url_with_query_params():
    url, item_id = normalize_item_url("https://www.ebay.com/itm/123456789?hash=item123&foo=bar")
    assert item_id == "123456789"


def test_normalize_item_url_item_id_only():
    url, item_id = normalize_item_url("123456789")
    assert item_id == "123456789"
    assert "ebay.com/itm/123456789" in url


def test_normalize_item_url_invalid():
    with pytest.raises(ValueError, match="Could not extract"):
        normalize_item_url("not-a-valid-input")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_scraper_active.py -v`
Expected: FAIL — ImportError for parse_active_listing, extract_search_query, normalize_item_url

- [ ] **Step 4: Implement active listing scraper functions**

Add to the end of `src/ebay_tracker/scraper.py` (before the existing `rate_limit_delay` function):

```python
from ebay_tracker.models import ActiveListing, SuggestedQuery


def normalize_item_url(url_or_item_id: str) -> tuple[str, str]:
    url_or_item_id = url_or_item_id.strip()
    match = re.search(r"/itm/(\d+)", url_or_item_id)
    if match:
        item_id = match.group(1)
        return f"https://www.ebay.com/itm/{item_id}", item_id
    if url_or_item_id.isdigit():
        return f"https://www.ebay.com/itm/{url_or_item_id}", url_or_item_id
    raise ValueError(f"Could not extract item ID from: {url_or_item_id}")


def fetch_active_listing(url_or_item_id: str, proxy_url: str | None = None) -> ActiveListing:
    url, item_id = normalize_item_url(url_or_item_id)
    html = fetch_page(url, proxy_url)
    return parse_active_listing(html, item_id)


def parse_active_listing(html: str, item_id: str) -> ActiveListing:
    soup = BeautifulSoup(html, "lxml")

    title_elem = soup.select_one("h1.x-item-title__mainTitle span, h1.x-item-title__mainTitle")
    title = title_elem.get_text(strip=True) if title_elem else "Unknown"

    price_elem = soup.select_one(".x-price-primary span.ux-textspans")
    price = parse_price(price_elem.get_text(strip=True)) if price_elem else 0.0

    condition_elem = soup.select_one(".x-item-condition span.ux-textspans, .x-item-condition .ux-icon-text__text")
    condition = condition_elem.get_text(strip=True) if condition_elem else None

    shipping = None
    shipping_section = soup.select_one(".ux-labels-values--shipping .ux-labels-values__values-content")
    if shipping_section:
        shipping_text = shipping_section.get_text(strip=True)
        if "free" in shipping_text.lower():
            shipping = 0.0
        else:
            shipping = parse_price(shipping_text)

    seller = None
    seller_elem = soup.select_one(".x-sellercard-atf__info__about-seller span.ux-textspans--BOLD")
    if seller_elem:
        seller = seller_elem.get_text(strip=True)

    category_id = None
    breadcrumb_link = soup.select_one("nav.breadcrumbs a[href*='/b/']")
    if breadcrumb_link:
        href = breadcrumb_link.get("href", "")
        cat_match = re.search(r"/(\d+)/", href)
        if cat_match:
            category_id = int(cat_match.group(1))

    item_specifics = {}
    for dl in soup.select(".x-about-this-item dl.ux-labels-values"):
        label_elem = dl.select_one(".ux-labels-values__labels-content span")
        value_elem = dl.select_one(".ux-labels-values__values-content span")
        if label_elem and value_elem:
            label = label_elem.get_text(strip=True)
            value = value_elem.get_text(strip=True)
            if label and value:
                item_specifics[label] = value

    return ActiveListing(
        item_id=item_id,
        title=title,
        price=price,
        shipping=shipping,
        condition=condition,
        category_id=category_id,
        item_specifics=item_specifics,
        url=f"https://www.ebay.com/itm/{item_id}",
        seller=seller,
    )


def extract_search_query(listing: ActiveListing) -> SuggestedQuery:
    specs = listing.item_specifics
    query_parts = []

    brand = specs.get("Brand")
    if brand:
        query_parts.append(brand)

    style = specs.get("Style") or specs.get("Model")
    if style:
        query_parts.append(style)

    title_lower = listing.title.lower()
    clothing_keywords = ["jeans", "pants", "shirt", "jacket", "shorts", "sweater", "coat", "shoes", "boots"]
    for kw in clothing_keywords:
        if kw in title_lower and kw not in " ".join(query_parts).lower():
            query_parts.append(kw)
            break

    waist = specs.get("Waist Size")
    inseam = specs.get("Inseam")
    size = specs.get("Size")
    if waist and inseam:
        query_parts.append(f"{waist}x{inseam}")
    elif size:
        query_parts.append(size)

    if not query_parts:
        query_parts = listing.title.split()[:6]

    filters = {}
    if listing.condition:
        filters["condition"] = listing.condition
    if listing.category_id:
        filters["category"] = listing.category_id

    return SuggestedQuery(
        query=" ".join(query_parts),
        filters=filters,
        raw_attributes=dict(specs),
    )
```

Also update the imports at the top of `scraper.py` to include the new models:

Add `ActiveListing, SuggestedQuery` to the import from `ebay_tracker.models`:

```python
from ebay_tracker.models import Listing, ActiveListing, SuggestedQuery
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_scraper_active.py -v`
Expected: All 14 tests PASS

- [ ] **Step 6: Run all scraper tests**

Run: `uv run pytest tests/test_scraper.py tests/test_scraper_active.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/ebay_tracker/scraper.py tests/test_scraper_active.py tests/fixtures/ebay_active_listing.html
git commit -m "feat: add active listing scraper and query extraction"
```

---

### Task 6: Time-to-Sell Predictor

**Files:**
- Create: `src/ebay_tracker/prediction.py`
- Create: `tests/test_prediction.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_prediction.py`:

```python
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
    """25 listings spread over ~50 days at varying prices."""
    base = date(2025, 1, 1)
    listings = []
    for i in range(25):
        d = date.fromordinal(base.toordinal() + i * 2)
        price = 30.0 + (i % 5) * 5
        listings.append(_make_listing(d, price))
    return listings


@pytest.fixture
def few_comps():
    """3 listings — below threshold for log-normal."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_prediction.py -v`
Expected: FAIL — ModuleNotFoundError: No module named 'ebay_tracker.prediction'

- [ ] **Step 3: Implement prediction.py**

Create `src/ebay_tracker/prediction.py`:

```python
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
        median_price = np.median(prices)
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
        avg_interval = np.mean(intervals)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_prediction.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ebay_tracker/prediction.py tests/test_prediction.py
git commit -m "feat: add log-normal time-to-sell predictor"
```

---

### Task 7: Evaluator

**Files:**
- Create: `src/ebay_tracker/evaluator.py`
- Create: `tests/test_evaluator.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_evaluator.py`:

```python
import pytest
from datetime import date
from unittest.mock import patch, MagicMock

from ebay_tracker.models import ActiveListing, Listing, SuggestedQuery
from ebay_tracker.config import FeeConfig, ThresholdConfig
from ebay_tracker.evaluator import run_profit_analysis


def _make_active_listing(price: float = 25.00, shipping: float = 5.99) -> ActiveListing:
    return ActiveListing(
        item_id="123456",
        title="Levi's 501 Jeans 32x30",
        price=price,
        shipping=shipping,
        condition="Pre-owned",
        category_id=11483,
        item_specifics={"Brand": "Levi's"},
        url="https://www.ebay.com/itm/123456",
        seller="seller1",
    )


def _make_comps(prices: list[float], base_date: date = date(2025, 1, 1)) -> list[Listing]:
    comps = []
    for i, price in enumerate(prices):
        d = date.fromordinal(base_date.toordinal() + i * 3)
        comps.append(Listing(
            id=i, search_id=1, ebay_item_id=f"comp{i}",
            title=f"Comp {i}", price=price, shipping=0.0,
            condition="Pre-owned", sold_date=d,
            url=None, created_at=None,
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
    assert result.total_purchase_cost == 20.00 + 5.00 + expected_tax


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_evaluator.py -v`
Expected: FAIL — ModuleNotFoundError: No module named 'ebay_tracker.evaluator'

- [ ] **Step 3: Implement evaluator.py**

Create `src/ebay_tracker/evaluator.py`:

```python
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

    net_proceeds = calculator.calculate_net_proceeds(expected_sale_price)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_evaluator.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ebay_tracker/evaluator.py tests/test_evaluator.py
git commit -m "feat: add profit analysis evaluator"
```

---

### Task 8: CLI Evaluate Command

**Files:**
- Modify: `src/ebay_tracker/cli.py`

- [ ] **Step 1: Fix missing rate_limit_delay import**

In `src/ebay_tracker/cli.py`, update the scraper import (line 15) from:

```python
from ebay_tracker.scraper import build_search_url, fetch_page, parse_listings
```

to:

```python
from ebay_tracker.scraper import (
    build_search_url, fetch_page, parse_listings,
    fetch_active_listing, extract_search_query, rate_limit_delay,
)
```

- [ ] **Step 2: Add new imports for evaluate command**

Add after the existing imports at the top of `cli.py`:

```python
from ebay_tracker.config import FeeConfig, ThresholdConfig, UserPreferences
from ebay_tracker.evaluator import run_profit_analysis
```

Update the existing config import from:

```python
from ebay_tracker.config import get_config, get_user_prefs, save_user_prefs
```

to:

```python
from ebay_tracker.config import get_config, get_user_prefs, save_user_prefs, FeeConfig, ThresholdConfig
```

- [ ] **Step 3: Add the evaluate command**

Add before the `if __name__ == "__main__":` block at the end of `cli.py`:

```python
@app.command()
def evaluate(
    url_or_item_id: str = typer.Argument(..., help="eBay listing URL or item number"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Override comp search query"),
    min_profit_pct: Optional[float] = typer.Option(None, "--min-profit-pct", help="Min profit percentage threshold"),
    min_profit_dollar: Optional[float] = typer.Option(None, "--min-profit-dollar", help="Min profit dollar threshold"),
    threshold_mode: Optional[str] = typer.Option(None, "--threshold-mode", help="Threshold mode: 'and' or 'or'"),
    shipping_cost: Optional[float] = typer.Option(None, "--shipping-cost", help="Seller-paid shipping cost"),
    tax_rate: Optional[float] = typer.Option(None, "--tax-rate", help="Sales tax rate override (percentage)"),
    max_comps: int = typer.Option(240, "--max-comps", help="Max number of comps to fetch"),
    export_path: Optional[Path] = typer.Option(None, "--export", help="Export analysis to JSON file"),
):
    """Evaluate an eBay listing for resale profitability."""
    import json as json_mod
    config = get_config()
    prefs = get_user_prefs()

    fee_cfg = FeeConfig(
        final_value_pct=prefs.fees.final_value_pct,
        payment_processing_pct=prefs.fees.payment_processing_pct,
        payment_processing_flat=prefs.fees.payment_processing_flat,
        shipping_cost=shipping_cost if shipping_cost is not None else prefs.fees.shipping_cost,
        sales_tax_rate=tax_rate if tax_rate is not None else prefs.fees.sales_tax_rate,
        state=prefs.fees.state,
    )
    threshold_cfg = ThresholdConfig(
        min_profit_pct=min_profit_pct if min_profit_pct is not None else prefs.thresholds.min_profit_pct,
        min_profit_dollar=min_profit_dollar if min_profit_dollar is not None else prefs.thresholds.min_profit_dollar,
        mode=threshold_mode if threshold_mode is not None else prefs.thresholds.mode,
    )

    console.print("[cyan]Fetching listing...[/cyan]")
    try:
        active = fetch_active_listing(url_or_item_id, config.proxy_url)
    except Exception as e:
        console.print(f"[red]Failed to fetch listing: {e}[/red]")
        raise typer.Exit(1)

    table = Table(title="Active Listing", show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Title", active.title)
    table.add_row("Price", f"${active.price:.2f}")
    table.add_row("Shipping", f"${active.shipping:.2f}" if active.shipping else "N/A")
    table.add_row("Condition", active.condition or "N/A")
    table.add_row("Seller", active.seller or "N/A")
    if active.item_specifics:
        specs_str = ", ".join(f"{k}: {v}" for k, v in active.item_specifics.items())
        table.add_row("Specifics", specs_str)
    console.print(table)
    console.print()

    if query:
        comp_query = query
        comp_filters = {}
    else:
        suggested = extract_search_query(active)
        console.print(f"[cyan]Suggested search:[/cyan] {suggested.query}")
        if suggested.filters:
            console.print(f"[dim]Filters: {suggested.filters}[/dim]")
        console.print()

        choice = typer.prompt("Use this search? [Y/edit/abort]", default="Y")
        if choice.lower() == "abort":
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)
        elif choice.lower() in ("e", "edit"):
            comp_query = typer.prompt("Search query", default=suggested.query)
            comp_filters = suggested.filters
        else:
            comp_query = suggested.query
            comp_filters = suggested.filters

    console.print("[cyan]Fetching comparable sold listings...[/cyan]")
    try:
        url = build_search_url(comp_query, comp_filters)
        html = fetch_page(url, config.proxy_url)
        comps = parse_listings(html, search_id=0)
    except Exception as e:
        console.print(f"[red]Failed to fetch comps: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Found {len(comps)} comparable sales[/dim]")
    console.print()

    result = run_profit_analysis(active, comps, fee_cfg, threshold_cfg)

    result_table = Table(title="Profit Analysis")
    result_table.add_column("Metric", style="bold")
    result_table.add_column("Value", justify="right")

    result_table.add_row("Purchase Price", f"${result.purchase_price:.2f}")
    result_table.add_row("+ Shipping", f"${result.purchase_shipping:.2f}")
    if result.purchase_tax > 0:
        result_table.add_row("+ Sales Tax", f"${result.purchase_tax:.2f}")
    result_table.add_row("[bold]Total Cost[/bold]", f"[bold]${result.total_purchase_cost:.2f}[/bold]")
    result_table.add_row("", "")
    result_table.add_row("Expected Sale (median)", f"${result.expected_sale_price:.2f}")
    result_table.add_row("Sale Range (25th-75th)", f"${result.sale_price_25th:.2f} - ${result.sale_price_75th:.2f}")
    result_table.add_row("eBay Final Value Fee", f"-${result.net_proceeds.final_value_fee:.2f}")
    result_table.add_row("Payment Processing", f"-${result.net_proceeds.payment_processing_fee:.2f}")
    if result.net_proceeds.shipping_cost > 0:
        result_table.add_row("Seller Shipping", f"-${result.net_proceeds.shipping_cost:.2f}")
    result_table.add_row("[bold]Net Proceeds[/bold]", f"[bold]${result.net_proceeds.net:.2f}[/bold]")
    result_table.add_row("", "")

    profit_style = "green" if result.projected_profit > 0 else "red"
    result_table.add_row(
        f"[{profit_style}]Projected Profit[/{profit_style}]",
        f"[{profit_style}]${result.projected_profit:.2f} ({result.projected_profit_pct:.1f}%)[/{profit_style}]",
    )

    if result.time_to_sell:
        tts = result.time_to_sell
        result_table.add_row("", "")
        result_table.add_row("Time to Sell (median)", f"~{tts.median_days:.0f} days")
        result_table.add_row("  Quick / Slow / Max", f"{tts.fast_days:.0f}d / {tts.slow_days:.0f}d / {tts.ninety_pct_days:.0f}d")

    result_table.add_row("", "")
    result_table.add_row("Confidence", f"{result.confidence} ({result.comp_count} comps)")
    result_table.add_row("Threshold", result.threshold_detail)

    verdict_style = "bold green" if result.meets_threshold else "bold red"
    verdict_text = "BUY" if result.meets_threshold else "PASS"
    result_table.add_row(f"[{verdict_style}]Verdict[/{verdict_style}]", f"[{verdict_style}]{verdict_text}[/{verdict_style}]")

    console.print(result_table)

    if export_path:
        export_data = {
            "listing": {
                "item_id": active.item_id,
                "title": active.title,
                "price": active.price,
                "shipping": active.shipping,
                "condition": active.condition,
                "url": active.url,
            },
            "analysis": {
                "purchase_cost": result.total_purchase_cost,
                "expected_sale_price": result.expected_sale_price,
                "sale_range": [result.sale_price_25th, result.sale_price_75th],
                "net_proceeds": result.net_proceeds.net,
                "projected_profit": result.projected_profit,
                "projected_profit_pct": result.projected_profit_pct,
                "meets_threshold": result.meets_threshold,
                "threshold_detail": result.threshold_detail,
                "confidence": result.confidence,
                "comp_count": result.comp_count,
            },
        }
        if result.time_to_sell:
            export_data["analysis"]["time_to_sell"] = {
                "median_days": result.time_to_sell.median_days,
                "fast_days": result.time_to_sell.fast_days,
                "slow_days": result.time_to_sell.slow_days,
                "ninety_pct_days": result.time_to_sell.ninety_pct_days,
            }
        export_path.write_text(json_mod.dumps(export_data, indent=2))
        console.print(f"\n[green]Analysis exported to {export_path}[/green]")
```

- [ ] **Step 4: Verify the CLI help works**

Run: `uv run ebay-tracker evaluate --help`
Expected: Shows help text with all options for the evaluate command

- [ ] **Step 5: Run existing CLI tests to check for regressions**

Run: `uv run pytest tests/test_cli.py -v`
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/ebay_tracker/cli.py
git commit -m "feat: add evaluate CLI command for resale profitability"
```

---

### Task 9: MCP Server

**Files:**
- Create: `src/ebay_tracker/server.py`
- Create: `src/ebay_tracker/__main__.py`
- Create: `tests/test_server.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_server.py`:

```python
import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import date

from ebay_tracker.server import (
    _do_evaluate_listing,
    _do_run_profit_analysis,
    _do_configure_fees,
    _do_configure_thresholds,
    _do_get_historical_stats,
)
from ebay_tracker.models import ActiveListing, Listing


@pytest.fixture
def mock_active_listing():
    return ActiveListing(
        item_id="123456",
        title="Levi's 501 Jeans 32x30",
        price=25.00,
        shipping=5.99,
        condition="Pre-owned",
        category_id=11483,
        item_specifics={"Brand": "Levi's", "Style": "501"},
        url="https://www.ebay.com/itm/123456",
        seller="seller1",
    )


def test_do_evaluate_listing(mock_active_listing):
    with patch("ebay_tracker.server.fetch_active_listing", return_value=mock_active_listing):
        result = _do_evaluate_listing("123456")
    assert result["listing"]["item_id"] == "123456"
    assert result["listing"]["price"] == 25.00
    assert "suggested_query" in result
    assert result["suggested_query"]["query"] != ""


def test_do_run_profit_analysis(mock_active_listing):
    comps_data = [
        {"price": 45.0, "shipping": 0.0, "condition": "Pre-owned",
         "sold_date": "2025-01-05", "title": "Comp 1", "ebay_item_id": "c1"},
        {"price": 50.0, "shipping": 0.0, "condition": "Pre-owned",
         "sold_date": "2025-01-10", "title": "Comp 2", "ebay_item_id": "c2"},
        {"price": 48.0, "shipping": 0.0, "condition": "Pre-owned",
         "sold_date": "2025-01-15", "title": "Comp 3", "ebay_item_id": "c3"},
    ]
    listing_data = {
        "item_id": "123456",
        "title": "Levi's 501 Jeans 32x30",
        "price": 25.00,
        "shipping": 5.99,
        "condition": "Pre-owned",
        "category_id": 11483,
        "item_specifics": {},
        "url": "https://www.ebay.com/itm/123456",
        "seller": "seller1",
    }

    with patch("ebay_tracker.server.fetch_page") as mock_fetch, \
         patch("ebay_tracker.server.parse_listings") as mock_parse:
        mock_fetch.return_value = "<html></html>"
        mock_parse.return_value = [
            Listing(None, 0, c["ebay_item_id"], c["title"], c["price"], c["shipping"],
                    c["condition"], date.fromisoformat(c["sold_date"]), None, None)
            for c in comps_data
        ]
        result = _do_run_profit_analysis(
            listing_data=listing_data,
            comp_query="Levi's 501 jeans 32x30",
            comp_filters={},
        )

    assert "projected_profit" in result
    assert "meets_threshold" in result
    assert "verdict" in result
    assert result["comp_count"] == 3


def test_do_configure_fees(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr("ebay_tracker.config.get_prefs_path", lambda: config_path)
    monkeypatch.setattr("ebay_tracker.server.get_prefs_path", lambda: config_path)

    result = _do_configure_fees(shipping_cost=8.50, sales_tax_rate=7.0, state="TX")
    assert result["fees"]["shipping_cost"] == 8.50
    assert result["fees"]["sales_tax_rate"] == 7.0
    assert result["fees"]["state"] == "TX"


def test_do_configure_thresholds(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr("ebay_tracker.config.get_prefs_path", lambda: config_path)
    monkeypatch.setattr("ebay_tracker.server.get_prefs_path", lambda: config_path)

    result = _do_configure_thresholds(min_profit_pct=25.0, mode="or")
    assert result["thresholds"]["min_profit_pct"] == 25.0
    assert result["thresholds"]["mode"] == "or"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_server.py -v`
Expected: FAIL — ModuleNotFoundError: No module named 'ebay_tracker.server'

- [ ] **Step 3: Implement server.py**

Create `src/ebay_tracker/server.py`:

```python
import json
from datetime import date

from mcp.server.fastmcp import FastMCP

from ebay_tracker.config import (
    FeeConfig, ThresholdConfig,
    get_config, get_prefs_path, get_user_prefs, save_user_prefs,
)
from ebay_tracker.evaluator import run_profit_analysis as _run_analysis
from ebay_tracker.models import ActiveListing, Listing
from ebay_tracker.scraper import (
    build_search_url, extract_search_query,
    fetch_active_listing, fetch_page, parse_listings,
)

mcp = FastMCP(
    "ebay-resale",
    instructions=(
        "eBay resale profit analysis. Use evaluate_listing first to inspect a listing, "
        "then run_profit_analysis with a confirmed comp query. "
        "Use configure_fees/configure_thresholds to set user preferences."
    ),
)


def _listing_to_dict(listing: ActiveListing) -> dict:
    return {
        "item_id": listing.item_id,
        "title": listing.title,
        "price": listing.price,
        "shipping": listing.shipping,
        "condition": listing.condition,
        "category_id": listing.category_id,
        "item_specifics": listing.item_specifics,
        "url": listing.url,
        "seller": listing.seller,
    }


def _do_evaluate_listing(url_or_item_id: str) -> dict:
    config = get_config()
    listing = fetch_active_listing(url_or_item_id, config.proxy_url)
    suggested = extract_search_query(listing)
    return {
        "listing": _listing_to_dict(listing),
        "suggested_query": {
            "query": suggested.query,
            "filters": suggested.filters,
            "raw_attributes": suggested.raw_attributes,
        },
    }


def _do_run_profit_analysis(
    listing_data: dict,
    comp_query: str,
    comp_filters: dict | None = None,
    fee_overrides: dict | None = None,
    threshold_overrides: dict | None = None,
) -> dict:
    config = get_config()
    prefs = get_user_prefs()

    listing = ActiveListing(
        item_id=listing_data["item_id"],
        title=listing_data["title"],
        price=listing_data["price"],
        shipping=listing_data.get("shipping"),
        condition=listing_data.get("condition"),
        category_id=listing_data.get("category_id"),
        item_specifics=listing_data.get("item_specifics", {}),
        url=listing_data.get("url", ""),
        seller=listing_data.get("seller"),
    )

    fee_cfg = FeeConfig(
        final_value_pct=(fee_overrides or {}).get("final_value_pct", prefs.fees.final_value_pct),
        payment_processing_pct=(fee_overrides or {}).get("payment_processing_pct", prefs.fees.payment_processing_pct),
        payment_processing_flat=(fee_overrides or {}).get("payment_processing_flat", prefs.fees.payment_processing_flat),
        shipping_cost=(fee_overrides or {}).get("shipping_cost", prefs.fees.shipping_cost),
        sales_tax_rate=(fee_overrides or {}).get("sales_tax_rate", prefs.fees.sales_tax_rate),
    )
    threshold_cfg = ThresholdConfig(
        min_profit_pct=(threshold_overrides or {}).get("min_profit_pct", prefs.thresholds.min_profit_pct),
        min_profit_dollar=(threshold_overrides or {}).get("min_profit_dollar", prefs.thresholds.min_profit_dollar),
        mode=(threshold_overrides or {}).get("mode", prefs.thresholds.mode),
    )

    url = build_search_url(comp_query, comp_filters)
    html = fetch_page(url, config.proxy_url)
    comps = parse_listings(html, search_id=0)

    result = _run_analysis(listing, comps, fee_cfg, threshold_cfg)

    output = {
        "purchase_cost": result.total_purchase_cost,
        "expected_sale_price": result.expected_sale_price,
        "sale_price_25th": result.sale_price_25th,
        "sale_price_75th": result.sale_price_75th,
        "net_proceeds": result.net_proceeds.net,
        "fees": {
            "final_value_fee": result.net_proceeds.final_value_fee,
            "payment_processing_fee": result.net_proceeds.payment_processing_fee,
            "shipping_cost": result.net_proceeds.shipping_cost,
            "total_fees": result.net_proceeds.total_fees,
        },
        "projected_profit": result.projected_profit,
        "projected_profit_pct": result.projected_profit_pct,
        "meets_threshold": result.meets_threshold,
        "threshold_detail": result.threshold_detail,
        "verdict": "BUY" if result.meets_threshold else "PASS",
        "confidence": result.confidence,
        "comp_count": result.comp_count,
    }

    if result.time_to_sell:
        output["time_to_sell"] = {
            "median_days": result.time_to_sell.median_days,
            "fast_days": result.time_to_sell.fast_days,
            "slow_days": result.time_to_sell.slow_days,
            "ninety_pct_days": result.time_to_sell.ninety_pct_days,
            "confidence": result.time_to_sell.confidence,
            "price_tier": result.time_to_sell.price_tier,
        }

    return output


def _do_configure_fees(**kwargs) -> dict:
    prefs = get_user_prefs()
    for key, value in kwargs.items():
        if value is not None and hasattr(prefs.fees, key):
            setattr(prefs.fees, key, value)
    save_user_prefs(prefs)
    return {
        "fees": {
            "final_value_pct": prefs.fees.final_value_pct,
            "payment_processing_pct": prefs.fees.payment_processing_pct,
            "payment_processing_flat": prefs.fees.payment_processing_flat,
            "shipping_cost": prefs.fees.shipping_cost,
            "sales_tax_rate": prefs.fees.sales_tax_rate,
            "state": prefs.fees.state,
        }
    }


def _do_configure_thresholds(**kwargs) -> dict:
    prefs = get_user_prefs()
    for key, value in kwargs.items():
        if value is not None and hasattr(prefs.thresholds, key):
            setattr(prefs.thresholds, key, value)
    save_user_prefs(prefs)
    return {
        "thresholds": {
            "min_profit_pct": prefs.thresholds.min_profit_pct,
            "min_profit_dollar": prefs.thresholds.min_profit_dollar,
            "mode": prefs.thresholds.mode,
        }
    }


def _do_get_historical_stats(search_name: str) -> dict:
    from ebay_tracker.analyzer import analyze_listings
    from ebay_tracker.db import Database

    config = get_config()
    db = Database(config.db_path)
    db.init()

    search = db.get_search_by_name(search_name)
    if not search:
        db.close()
        return {"error": f"Search '{search_name}' not found"}

    listings = db.get_listings_for_search(search.id)
    db.close()

    if not listings:
        return {"search": search_name, "count": 0, "message": "No data. Run fetch first."}

    stats = analyze_listings(listings)
    return {"search": search_name, **stats}


@mcp.tool()
def evaluate_listing(url_or_item_id: str) -> str:
    """Fetch an active eBay listing and generate a suggested comp search query.
    Returns listing details and suggested query for review before running full analysis.
    Input: eBay listing URL (e.g. https://www.ebay.com/itm/123456) or item number."""
    result = _do_evaluate_listing(url_or_item_id)
    return json.dumps(result, indent=2)


@mcp.tool()
def run_profit_analysis(
    listing_data: str,
    comp_query: str,
    comp_filters: str = "{}",
    fee_overrides: str = "{}",
    threshold_overrides: str = "{}",
) -> str:
    """Run full resale profit analysis. Call evaluate_listing first, then pass listing_data
    from its response with a confirmed comp_query.
    listing_data: JSON string of listing details from evaluate_listing.
    comp_query: Search query for comparable sold items.
    comp_filters: JSON string of optional filters (condition, category, etc.).
    fee_overrides: JSON string to override fee settings for this analysis.
    threshold_overrides: JSON string to override threshold settings for this analysis."""
    result = _do_run_profit_analysis(
        listing_data=json.loads(listing_data),
        comp_query=comp_query,
        comp_filters=json.loads(comp_filters) if comp_filters else None,
        fee_overrides=json.loads(fee_overrides) if fee_overrides else None,
        threshold_overrides=json.loads(threshold_overrides) if threshold_overrides else None,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def configure_fees(
    final_value_pct: float | None = None,
    payment_processing_pct: float | None = None,
    payment_processing_flat: float | None = None,
    shipping_cost: float | None = None,
    sales_tax_rate: float | None = None,
    state: str | None = None,
) -> str:
    """Get or set fee configuration. Pass parameters to update, or call with no args to read current config.
    Persists to ~/.config/ebay-tracker/config.json."""
    kwargs = {
        "final_value_pct": final_value_pct,
        "payment_processing_pct": payment_processing_pct,
        "payment_processing_flat": payment_processing_flat,
        "shipping_cost": shipping_cost,
        "sales_tax_rate": sales_tax_rate,
        "state": state,
    }
    result = _do_configure_fees(**{k: v for k, v in kwargs.items() if v is not None})
    return json.dumps(result, indent=2)


@mcp.tool()
def configure_thresholds(
    min_profit_pct: float | None = None,
    min_profit_dollar: float | None = None,
    mode: str | None = None,
) -> str:
    """Get or set profit threshold configuration. Mode is 'and' (both must pass) or 'or' (either passes).
    Persists to ~/.config/ebay-tracker/config.json."""
    kwargs = {
        "min_profit_pct": min_profit_pct,
        "min_profit_dollar": min_profit_dollar,
        "mode": mode,
    }
    result = _do_configure_thresholds(**{k: v for k, v in kwargs.items() if v is not None})
    return json.dumps(result, indent=2)


@mcp.tool()
def get_historical_stats(search_name: str) -> str:
    """Get price statistics and trends for an existing saved search.
    Queries the local database without making new eBay requests.
    search_name: Name of a search previously added via 'ebay-tracker add'."""
    result = _do_get_historical_stats(search_name)
    return json.dumps(result, indent=2)
```

- [ ] **Step 4: Create __main__.py entry point**

Create `src/ebay_tracker/__main__.py`:

```python
from ebay_tracker.server import mcp

mcp.run()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_server.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Verify MCP server starts**

Run: `uv run python -c "from ebay_tracker.server import mcp; print(f'Server: {mcp.name}, Tools: {len(mcp._tool_manager._tools)}')"` 
Expected: Prints server name and tool count (5 tools)

- [ ] **Step 7: Commit**

```bash
git add src/ebay_tracker/server.py src/ebay_tracker/__main__.py tests/test_server.py
git commit -m "feat: add MCP server with 5 tools for agent-driven analysis"
```

---

### Task 10: Plugin & Skill Files

**Files:**
- Create: `.claude-plugin/plugin.json` (at repo root, NOT inside eBay-analysis-toolkit/)
- Create: `.mcp.json` (at repo root)
- Create: `skills/evaluate/SKILL.md` (at repo root)

Note: The plugin files go at the repo root (`C:\Users\shurley\source\repos\HurleySk\eBay-analysis-toolkit\`), not inside the Python package subdirectory.

- [ ] **Step 1: Create plugin.json**

Create `.claude-plugin/plugin.json` at the repo root:

```json
{
  "name": "ebay-resale",
  "version": "0.1.0",
  "description": "eBay resale profit analysis — evaluate listings for buy/resell profitability",
  "author": {
    "name": "HurleySk"
  },
  "license": "MIT",
  "homepage": "https://github.com/HurleySk/eBay-analysis-toolkit",
  "repository": "https://github.com/HurleySk/eBay-analysis-toolkit",
  "keywords": ["ebay", "resale", "profit", "analysis", "mcp"]
}
```

- [ ] **Step 2: Create .mcp.json**

Create `.mcp.json` at the repo root:

```json
{
  "mcpServers": {
    "ebay-resale": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "{PLUGIN_DIR}/eBay-analysis-toolkit", "python", "-m", "ebay_tracker"]
    }
  }
}
```

- [ ] **Step 3: Create the evaluate skill**

Create `skills/evaluate/SKILL.md` at the repo root:

```markdown
---
name: evaluate
description: Evaluate an eBay listing for resale profitability using historical sold comps
---

# eBay Resale Evaluation

Guide the user through evaluating an eBay listing for resale profitability.

## Workflow

1. **Get the listing** — Ask the user for an eBay listing URL or item number.

2. **Fetch listing details** — Call `evaluate_listing` with the URL/item ID. Present the listing details (title, price, condition, shipping) and the suggested comp search query to the user.

3. **Confirm the search** — Ask: "Does this search look right for finding comparable sold items? You can modify it if needed." Wait for confirmation or edits.

4. **Run the analysis** — Call `run_profit_analysis` with:
   - `listing_data`: the listing object from step 2
   - `comp_query`: the confirmed search query
   - `comp_filters`: any filters from the suggested query

5. **Present results** — Show the user:
   - Purchase cost breakdown
   - Expected sale price range (25th / median / 75th percentile)
   - Fee breakdown
   - **Projected profit** (amount and percentage)
   - Time-to-sell estimate (if available)
   - **Verdict**: BUY or PASS

6. **Google Sheets** (if requested) — Format the analysis as structured data and use a Google Sheets MCP to write it to the user's spreadsheet.

## Configuration

Before first use, help the user configure their fee settings:
- Call `configure_fees` to set shipping cost (if seller-paid) and sales tax rate for their state
- Call `configure_thresholds` to set profit percentage and dollar minimums

## Available Tools

| Tool | Purpose |
|------|---------|
| `evaluate_listing` | Fetch listing + generate suggested query |
| `run_profit_analysis` | Full analysis with fees, prediction, verdict |
| `configure_fees` | Set/get fee parameters |
| `configure_thresholds` | Set/get profit thresholds |
| `get_historical_stats` | Query existing saved search data |
```

- [ ] **Step 4: Commit**

```bash
git add .claude-plugin/plugin.json .mcp.json skills/evaluate/SKILL.md
git commit -m "feat: add Claude Code plugin, MCP config, and evaluate skill"
```

---

### Task 11: GitHub Actions

**Files:**
- Create: `.github/workflows/version-bump.yml` (at repo root)

- [ ] **Step 1: Create the workflow file**

Create `.github/workflows/version-bump.yml` at the repo root:

```yaml
name: Marketplace Sync

on:
  push:
    branches: [master]

permissions:
  contents: write

jobs:
  sync:
    if: github.actor != 'github-actions[bot]'
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.version.outputs.version }}
      plugin_name: ${{ steps.version.outputs.plugin_name }}
      bumped: ${{ steps.version.outputs.bumped }}
      release: ${{ steps.version.outputs.release }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2

      - name: Resolve version
        id: version
        run: |
          CURRENT=$(jq -r '.version' .claude-plugin/plugin.json)
          PLUGIN_NAME=$(jq -r '.name' .claude-plugin/plugin.json)
          COMMIT_MSG=$(git log -1 --format=%s)

          echo "plugin_name=$PLUGIN_NAME" >> "$GITHUB_OUTPUT"

          if echo "$COMMIT_MSG" | grep -q '\[release\]'; then
            echo "release=true" >> "$GITHUB_OUTPUT"

            PREV=$(git show HEAD~1:.claude-plugin/plugin.json 2>/dev/null | jq -r '.version' 2>/dev/null || echo "")
            if [ -n "$PREV" ] && [ "$PREV" != "$CURRENT" ]; then
              echo "Version already bumped locally: $PREV -> $CURRENT"
              echo "version=$CURRENT" >> "$GITHUB_OUTPUT"
              echo "bumped=false" >> "$GITHUB_OUTPUT"
            else
              IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT"
              NEW_VERSION="$MAJOR.$MINOR.$((PATCH + 1))"
              echo "Release requested — bumping: $CURRENT -> $NEW_VERSION"
              jq --arg v "$NEW_VERSION" '.version = $v' .claude-plugin/plugin.json > tmp.json
              mv tmp.json .claude-plugin/plugin.json
              echo "version=$NEW_VERSION" >> "$GITHUB_OUTPUT"
              echo "bumped=true" >> "$GITHUB_OUTPUT"
            fi
          else
            echo "No release tag — syncing current version: $CURRENT"
            echo "version=$CURRENT" >> "$GITHUB_OUTPUT"
            echo "bumped=false" >> "$GITHUB_OUTPUT"
            echo "release=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Commit version bump
        if: steps.version.outputs.bumped == 'true'
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add .claude-plugin/plugin.json
          git commit -m "[release] v${{ steps.version.outputs.version }}"
          git push

      - name: Create version tag
        if: steps.version.outputs.release == 'true'
        run: |
          git tag "v${{ steps.version.outputs.version }}"
          git push origin "v${{ steps.version.outputs.version }}"

  notify-marketplace:
    needs: sync
    runs-on: ubuntu-latest
    steps:
      - name: Dispatch to marketplace
        run: |
          curl -X POST \
            -H "Accept: application/vnd.github+v3+json" \
            -H "Authorization: Bearer ${{ secrets.MARKETPLACE_PAT }}" \
            https://api.github.com/repos/HurleySk/claude-plugins-marketplace/dispatches \
            -d "{\"event_type\":\"plugin-version-update\",\"client_payload\":{\"plugin_name\":\"${{ needs.sync.outputs.plugin_name }}\",\"version\":\"${{ needs.sync.outputs.version }}\"}}"
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/version-bump.yml
git commit -m "ci: add marketplace sync workflow"
```

---

### Task 12: Marketplace Entry

**Files:**
- Modify: `C:\Users\shurley\source\repos\HurleySk\hurleysk-marketplace\.claude-plugin\marketplace.json`

- [ ] **Step 1: Add ebay-resale plugin entry**

Add to the `plugins` array in the marketplace.json:

```json
{
  "name": "ebay-resale",
  "source": {
    "source": "url",
    "url": "https://github.com/HurleySk/eBay-analysis-toolkit"
  },
  "description": "eBay resale profit analysis — evaluate listings for buy/resell profitability",
  "version": "0.1.0"
}
```

- [ ] **Step 2: Commit in the marketplace repo**

```bash
cd C:\Users\shurley\source\repos\HurleySk\hurleysk-marketplace
git add .claude-plugin/marketplace.json
git commit -m "feat: add ebay-resale plugin"
```

---

### Task 13: Run Full Test Suite

- [ ] **Step 1: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS across all test files

- [ ] **Step 2: Run ruff linting**

Run: `uv run ruff check src/ tests/`
Expected: No lint errors (or fix any that appear)

- [ ] **Step 3: Verify CLI end-to-end**

Run: `uv run ebay-tracker --help`
Expected: Shows all commands including `evaluate`

Run: `uv run ebay-tracker evaluate --help`
Expected: Shows evaluate command options

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: resolve lint issues and test failures"
```
