# Comp Search Quality Improvement

## Problem

The `extract_search_query` function generates overly broad queries, resulting in heavily contaminated comps. For a "Rancourt Gilman Camp-moc" listing, the query "Rancourt Camp Moc" returns 240 results where only 29% are actually Rancourt products and only 5% are the Gilman model. The contaminated median ($56) is half the Rancourt-only median ($115), making the analysis useless.

## Design

Two layers: smarter query generation and post-fetch comp quality controls.

### 1. Query Generation (`extract_search_query`)

Current logic: `Brand + Style` (drops Model entirely).

New logic:
1. If Model exists and contains Brand, use Model as the query
2. If Model exists without Brand, use `Brand + Model`
3. If no Model, fall back to `Brand + Style` (current behavior)
4. Stop appending generic clothing keywords ("shoes", "boots") when a specific model is present
5. Shoe sizes: add `US Shoe Size` to `filters` dict for eBay aspect filtering instead of query text

**Files:** `src/ebay_tracker/scraper.py` — `extract_search_query()`

### 2. Comp Filtering (`_do_run_profit_analysis`)

Add a `filter_brand` parameter to `run_profit_analysis`. When set, only keep comps whose title contains the brand (case-insensitive). Applied after fetch, before analysis.

Price outlier removal: drop comps outside 1.5x IQR (standard box-plot rule). Applied after brand filtering.

If filtering removes all comps, fall back to unfiltered results with a warning in the response.

**Files:** `src/ebay_tracker/server.py` — `_do_run_profit_analysis()` and `run_profit_analysis()`

### 3. Response Enrichment

Add to the `run_profit_analysis` response:
- `comp_sample`: first 10 comp titles + prices (agent can eyeball quality)
- `brand_match_rate`: percentage of comps containing the brand name
- `comp_quality_warning`: set when brand match rate < 50% (e.g., "Only 29% of comps match brand 'Rancourt'")
- `comps_before_filter` / `comps_after_filter`: counts showing how many were removed

**Files:** `src/ebay_tracker/server.py` — response dict in `_do_run_profit_analysis()`

### 4. MCP Tool Interface

Add `filter_brand` as an optional string parameter to `run_profit_analysis`:
```
filter_brand: str = "" — Brand name to filter comps by (case-insensitive title match)
```

The evaluate skill workflow already has a confirm step where the agent can decide to pass `filter_brand` based on the listing's brand.

## Edge Cases

- **No comps after filtering:** Return unfiltered results with `"comp_quality_warning": "All comps removed by brand filter, showing unfiltered results"`
- **Brand not in listing specs:** `filter_brand` defaults to empty (no filtering), agent decides
- **Model field absent:** Falls back to current Brand + Style query (no regression)
- **Model field is just the brand name:** Same as current behavior (Brand + Style fallback since Model adds nothing)

## Testing

- Test `extract_search_query` with the Rancourt listing: should produce "Rancourt Gilman Camp-moc"
- Test brand filtering: given 240 comps, filtering on "Rancourt" should keep ~69
- Test IQR outlier removal: verify extreme prices are dropped
- Test edge case: all comps filtered out triggers fallback
- Integration test: run full analysis on Rancourt listing, verify median ~$115 vs old ~$56
