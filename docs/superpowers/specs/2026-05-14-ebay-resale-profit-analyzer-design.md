# eBay Resale Profit Analyzer — Design Spec

**Date:** 2026-05-14
**Status:** Approved
**Approach:** Single-repo enhancement (Approach 1)

## Overview

Enhance the existing eBay analysis toolkit to evaluate whether a specific eBay listing is worth purchasing for resale. The tool compares an active listing against historical sold comps, calculates projected profit after fees, predicts time-to-sell using a log-normal model, and returns a buy/pass verdict based on configurable thresholds.

The functionality is exposed through three interfaces:
1. **CLI command** (`ebay-tracker evaluate`) for direct user execution
2. **MCP server** (Python, stdio transport) for agent-driven workflows
3. **Claude Code plugin** in the HurleySk marketplace with extensible skills

## Architecture

All three interfaces share the same core modules. The MCP server and CLI are thin entry points into the same logic.

```
src/ebay_tracker/
├── analyzer.py        (existing — reused for comp stats)
├── categories.py      (existing — unchanged)
├── cli.py             (existing — new `evaluate` command added)
├── config.py          (existing — extended with fees/thresholds)
├── db.py              (existing — unchanged)
├── evaluator.py       (NEW — orchestrates profit analysis)
├── fees.py            (NEW — fee calculation engine)
├── models.py          (existing — new ActiveListing, ProfitAnalysis models)
├── prediction.py      (NEW — log-normal time-to-sell model)
├── scraper.py         (existing — new fetch_active_listing, extract_search_query)
└── server.py          (NEW — MCP server entry point)
```

Plugin structure at repo root:
```
eBay-analysis-toolkit/
├── .claude-plugin/
│   └── plugin.json
├── .mcp.json
├── skills/
│   └── evaluate/
│       └── SKILL.md
└── eBay-analysis-toolkit/   (existing Python package)
```

## Section 1: Core Profit Analysis Engine

### `fees.py` — Fee Calculator

`eBayFeeCalculator` class with configurable parameters:

| Fee | Default | Notes |
|-----|---------|-------|
| Final value fee | 13.25% | Configurable per category (rates vary) |
| Payment processing | 2.35% + $0.30 | eBay managed payments standard |
| Shipping cost | $0.00 | Configurable; $0 when buyer-paid |
| Sales tax rate | 0.00% | Configurable per state |

**Key method:** `calculate_net_proceeds(sale_price, shipping_to_buyer) -> NetProceeds`

```python
@dataclass
class NetProceeds:
    gross: float                # sale_price + shipping_to_buyer
    final_value_fee: float
    payment_processing_fee: float
    shipping_cost: float        # seller-paid shipping (0 if buyer-paid)
    total_fees: float
    net: float                  # gross - total_fees
```

Fee profiles persist in the user's config file (`~/.config/ebay-tracker/config.json`) so settings are configured once.

### `evaluator.py` — Analysis Orchestrator

Takes an active listing (URL or item #) and a confirmed comp search query. Orchestrates:

1. Fetch active listing details via scraper (price, condition, title, shipping)
2. Fetch historical sold comps via existing `fetch_sold_listings`
3. Run statistical analysis on comps via existing `analyzer.py`
4. Apply fee calculator to determine net proceeds at various price points
5. Compare purchase cost vs. expected net proceeds
6. Run time-to-sell prediction

**Output:**

```python
@dataclass
class ProfitAnalysis:
    # Purchase side
    purchase_price: float           # listing price
    purchase_shipping: float        # shipping to buy it
    purchase_tax: float             # sales tax on purchase (buyer's state rate * purchase_price)
    total_purchase_cost: float      # purchase_price + purchase_shipping + purchase_tax

    # Sale side (expected)
    expected_sale_price: float      # median comp price
    sale_price_25th: float          # 25th percentile — conservative
    sale_price_75th: float          # 75th percentile — optimistic
    net_proceeds: NetProceeds       # after eBay fees at median sale price

    # Profit
    projected_profit: float         # net_proceeds.net - total_purchase_cost
    projected_profit_pct: float     # profit as % of purchase cost
    meets_threshold: bool           # pass/fail against configured thresholds
    threshold_detail: str           # explanation of AND/OR evaluation

    # Prediction
    time_to_sell: SellTimePrediction | None
    confidence: str                 # "high", "medium", "low" based on comp count
    comp_count: int
    comps: list[Listing]            # the comp listings used
```

**Note on tax:** `purchase_tax` is the sales tax paid when *buying* the item (based on buyer's state rate). eBay fees on the *resale* side are handled by the fee calculator — eBay collects and remits sales tax on the resale automatically, so the seller doesn't need to account for it separately.

## Section 2: Active Listing Scraper & Comp Matching

### Extending `scraper.py`

**`fetch_active_listing(url_or_item_id) -> ActiveListing`**
- Accepts full URL (`ebay.com/itm/123456`) or item number
- Fetches through Decodo residential proxy
- Parses: title, asking price, shipping cost, condition, seller info, category, item specifics (brand, size, color, etc.)

**`extract_search_query(active_listing) -> SuggestedQuery`**
- Parses listing title + item specifics to build a suggested comp search
- Extracts key attributes: brand, model/style, size, condition
- Returns:
  - `query`: suggested search string (e.g., "Levi's 501 jeans 32x30")
  - `filters`: suggested filters dict (condition, category, price range)
  - `raw_attributes`: extracted attributes for user/agent review
- User/agent reviews and can modify before the comp search runs

Comp search reuses the existing `build_search_url()` + `fetch_sold_listings()` + `parse_listings()` pipeline unchanged.

### New Model in `models.py`

```python
@dataclass
class ActiveListing:
    item_id: str
    title: str
    price: float
    shipping: float | None
    condition: str | None
    category_id: int | None
    item_specifics: dict    # brand, size, color, etc.
    url: str
    seller: str | None

@dataclass
class SuggestedQuery:
    query: str
    filters: dict
    raw_attributes: dict
```

## Section 3: Time-to-Sell Prediction (Log-Normal Model)

### `prediction.py`

**`TimeToSellPredictor` class:**
- Input: list of sold comp listings (with `sold_date`) + target price point
- Calculates inter-sale intervals from comp data (gaps between consecutive sold dates)
- Fits a log-normal distribution using `scipy.stats.lognorm.fit()` on interval data
- Price-adjusts by splitting comps into tiers relative to median:
  - Below median price -> shorter predicted time
  - Above median price -> longer predicted time
  - Target price's percentile rank determines tier

**Output:**

```python
@dataclass
class SellTimePrediction:
    median_days: float          # 50th percentile — "most likely"
    fast_days: float            # 25th percentile — "if it moves quick"
    slow_days: float            # 75th percentile — "if it takes a while"
    ninety_pct_days: float      # 90th percentile — "worst realistic case"
    confidence: str             # "high" (20+ comps), "medium" (10-19), "low" (<10)
    sample_size: int
    price_tier: str             # "below_median", "at_median", "above_median"
```

**Fallback behavior:**
- Fewer than 5 comps with dates: skip log-normal fit, fall back to simple frequency-based estimate (listings per month from existing analyzer) with "low confidence" flag
- Zero comps: return `None`, evaluator reports "insufficient data"

**New dependency:** `scipy>=1.11.0` added to `pyproject.toml`

## Section 4: CLI Integration

### New Command: `ebay-tracker evaluate`

```
ebay-tracker evaluate <url-or-item-id> [options]
```

**Options:**

| Flag | Description | Default |
|------|-------------|---------|
| `--query` / `-q` | Override auto-extracted comp search query | Auto-extracted |
| `--min-profit-pct` | Minimum profit percentage threshold | From config |
| `--min-profit-dollar` | Minimum profit dollar threshold | From config |
| `--threshold-mode` | `and` or `or` | From config (`and`) |
| `--shipping-cost` | Seller-paid shipping cost | From config ($0) |
| `--tax-rate` | Sales tax rate override | From config (0%) |
| `--max-comps` | Max comps to fetch | 240 |
| `--export` | Export analysis to JSON file | None |

**Interactive flow (no `--query`):**
1. Fetch active listing, display details in Rich panel
2. Show auto-extracted suggested search query and filters
3. Prompt: "Use this search? [Y/edit/abort]"
4. If edit: let user modify query inline
5. Fetch comps, run analysis
6. Display results in Rich table:
   - Purchase cost breakdown
   - Expected sale range (25th / median / 75th percentile)
   - Fee breakdown
   - Projected profit (green/red highlight based on threshold)
   - Time-to-sell estimate with confidence intervals
   - Verdict: "BUY" or "PASS" based on thresholds

**Non-interactive flow (`--query` provided):**
- Skips confirmation prompt, runs straight through for scripting/piping

## Section 5: MCP Server

### `server.py` — Python MCP Server

Entry point: `python -m ebay_tracker.server`
Transport: stdio
SDK: `mcp>=1.0.0` (PyPI)

### Tools (5 tools)

**1. `evaluate_listing`**
- Input: `url_or_item_id` (string)
- Fetches active listing details and generates suggested comp query
- Returns: listing details + suggested query for agent/user review
- Does NOT run full analysis — allows query refinement first

**2. `run_profit_analysis`**
- Input: active listing data + confirmed comp query + optional fee/threshold overrides
- Fetches comps, runs full analysis
- Returns: structured `ProfitAnalysis` result (profit, fees, time-to-sell, verdict)

**3. `configure_fees`**
- Input: fee parameters (any subset)
- Get or set fee configuration
- Persists to user's config file

**4. `configure_thresholds`**
- Input: threshold parameters (any subset)
- Get or set profit thresholds (percentage, dollar, AND/OR mode)
- Persists to config

**5. `get_historical_stats`**
- Input: search name or query
- Lightweight query against existing saved searches/listings in database
- Returns trend data without a new scrape
- Reuses existing analyzer functions

**Design rationale for two-step evaluate/analyze split:** Lets the agent present the extracted query to the user for review before the expensive comp scrape runs.

## Section 6: Plugin & Marketplace

### Plugin Structure

**`.claude-plugin/plugin.json`:**
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

No hooks — tool-only plugin. The MCP server provides all functionality.

**`.mcp.json`:**
```json
{
  "mcpServers": {
    "ebay-resale": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "<plugin-dir>", "python", "-m", "ebay_tracker.server"]
    }
  }
}
```

### Skills

**`skills/evaluate/SKILL.md`** — Agent workflow guidance:
1. Ask user for eBay listing URL or item number
2. Call `evaluate_listing` to fetch details and suggested query
3. Present listing + suggested query to user for confirmation
4. Call `run_profit_analysis` with confirmed query
5. Present results: profit, time-to-sell, verdict
6. If user wants spreadsheet output, format analysis as structured data and use Google Sheets MCP to write it

Skills directory is extensible — future skills added as new subdirectories.

### Marketplace Entry

Add entry to `hurleysk-marketplace` `.claude-plugin/marketplace.json`:
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

### GitHub Actions — Marketplace Sync

Replicate the skill-engine CI/CD pattern. Add `.github/workflows/version-bump.yml`:

**On push to master:**
1. **Resolve version** — reads version from `.claude-plugin/plugin.json`. If commit message contains `[release]`, auto-bumps patch version (or detects if already bumped locally).
2. **Commit version bump** — if version was bumped, commits and pushes the new version.
3. **Create version tag** — tags the release commit (e.g., `v0.1.0`).
4. **Notify marketplace** — dispatches `plugin-version-update` event to `HurleySk/claude-plugins-marketplace` via `MARKETPLACE_PAT` secret, triggering the marketplace's `sync-version.yml` workflow to update the registry.

This requires:
- A `MARKETPLACE_PAT` secret configured on the `eBay-analysis-toolkit` GitHub repo (a PAT with `repo` scope on the marketplace repo)
- The marketplace's existing `sync-version.yml` workflow handles the rest automatically

## Section 7: Configuration

### Extended `~/.config/ebay-tracker/config.json`

```json
{
  "gender_preference": "mens",
  "favorite_categories": [11483],
  "fees": {
    "final_value_pct": 13.25,
    "payment_processing_pct": 2.35,
    "payment_processing_flat": 0.30,
    "shipping_cost": 0.00,
    "sales_tax_rate": 0.00,
    "state": null
  },
  "thresholds": {
    "min_profit_pct": 20.0,
    "min_profit_dollar": 10.0,
    "mode": "and"
  }
}
```

- Existing fields (`gender_preference`, `favorite_categories`) unchanged
- New `fees` and `thresholds` sections
- CLI flags override config values per-invocation
- MCP tools (`configure_fees`, `configure_thresholds`) update this file persistently
- State-to-tax-rate: user sets their rate directly via config or MCP tool

### Environment Variables

No new env vars. Existing `DECODO_PROXY_URL` and `EBAY_TRACKER_DB_PATH` unchanged. Fees and thresholds are user preferences, not secrets.

### Dependencies Added

| Package | Version | Purpose |
|---------|---------|---------|
| `scipy` | >=1.11.0 | Log-normal distribution fitting |
| `mcp` | >=1.0.0 | Python MCP SDK |
