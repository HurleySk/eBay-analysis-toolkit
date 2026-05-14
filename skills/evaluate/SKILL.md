---
name: evaluate
description: Evaluate an eBay listing for resale profitability using historical sold comps
---

# eBay Resale Evaluation

Guide the user through evaluating an eBay listing for resale profitability.

## Workflow

1. **Get the listing** -- Ask the user for an eBay listing URL or item number.

2. **Fetch listing details** -- Call `evaluate_listing` with the URL/item ID. Present the listing details (title, price, condition, shipping) and the suggested comp search query to the user.

3. **Confirm the search** -- Ask: "Does this search look right for finding comparable sold items? You can modify it if needed." Wait for confirmation or edits.

4. **Run the analysis** -- Call `run_profit_analysis` with:
   - `listing_data`: the listing object from step 2
   - `comp_query`: the confirmed search query
   - `comp_filters`: any filters from the suggested query

5. **Present results** -- Show the user:
   - Purchase cost breakdown
   - Expected sale price range (25th / median / 75th percentile)
   - Fee breakdown
   - **Projected profit** (amount and percentage)
   - Time-to-sell estimate (if available)
   - **Verdict**: BUY or PASS

6. **Google Sheets** (if requested) -- Format the analysis as structured data and use a Google Sheets MCP to write it to the user's spreadsheet.

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
| `test_connection` | Test proxy and browser health |

## Troubleshooting

If `evaluate_listing` or `run_profit_analysis` fails, call `test_connection` first to check:
- Whether the Decodo proxy is configured and reachable
- Whether the Playwright browser is healthy
- Whether eBay is accessible through the proxy
