# Comp Search Quality Improvement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve comp search accuracy by generating tighter queries and filtering out non-matching comps, so the profit analysis reflects real market value instead of noise.

**Architecture:** Two-layer approach — (1) smarter query generation in `extract_search_query` that prefers Model over Style, (2) post-fetch filtering in `_do_run_profit_analysis` with brand matching and IQR outlier removal, plus response enrichment with comp quality metadata.

**Tech Stack:** Python, pytest, existing ebay_tracker modules

---

### Task 1: Smarter Query Generation — Tests

**Files:**
- Modify: `tests/test_scraper_active.py`

- [ ] **Step 1: Write failing tests for Model-based query generation**

Add these tests to `tests/test_scraper_active.py`:

```python
from ebay_tracker.models import ActiveListing
from ebay_tracker.scraper import extract_search_query


def test_extract_search_query_uses_model_when_contains_brand():
    """Model 'Rancourt Gilman Camp-moc' already contains brand — use it directly."""
    listing = ActiveListing(
        item_id="1", title="Rancourt Gilman Camp-moc Heritage Brown 9.5D",
        price=99.0, shipping=27.76, condition="Pre-owned", category_id=11450,
        item_specifics={
            "Brand": "Rancourt", "Style": "Camp Moc",
            "Model": "Rancourt Gilman Camp-moc",
        },
        url="", seller=None,
    )
    suggested = extract_search_query(listing)
    assert "Gilman" in suggested.query
    assert "Rancourt" in suggested.query


def test_extract_search_query_prepends_brand_when_model_lacks_it():
    """Model 'Gilman Camp-moc' doesn't contain brand — prepend it."""
    listing = ActiveListing(
        item_id="2", title="Gilman Camp-moc 10D",
        price=99.0, shipping=0.0, condition="Pre-owned", category_id=11450,
        item_specifics={
            "Brand": "Rancourt", "Style": "Camp Moc",
            "Model": "Gilman Camp-moc",
        },
        url="", seller=None,
    )
    suggested = extract_search_query(listing)
    assert suggested.query == "Rancourt Gilman Camp-moc"


def test_extract_search_query_falls_back_to_style_without_model():
    """No Model field — fall back to Brand + Style (existing behavior)."""
    listing = ActiveListing(
        item_id="3", title="Levi's 501 Jeans 32x30",
        price=25.0, shipping=5.99, condition="Pre-owned", category_id=11483,
        item_specifics={
            "Brand": "Levi's", "Style": "501",
            "Waist Size": "32", "Inseam": "30",
        },
        url="", seller=None,
    )
    suggested = extract_search_query(listing)
    assert "Levi's" in suggested.query
    assert "501" in suggested.query


def test_extract_search_query_no_generic_keyword_with_model():
    """When Model is present, don't append generic keywords like 'shoes'."""
    listing = ActiveListing(
        item_id="4", title="Rancourt Gilman Camp-moc Shoes Brown",
        price=99.0, shipping=0.0, condition="Pre-owned", category_id=11450,
        item_specifics={
            "Brand": "Rancourt", "Model": "Rancourt Gilman Camp-moc",
        },
        url="", seller=None,
    )
    suggested = extract_search_query(listing)
    assert "shoes" not in suggested.query.lower()


def test_extract_search_query_shoe_size_in_filters():
    """US Shoe Size should be in filters, not in query text."""
    listing = ActiveListing(
        item_id="5", title="Rancourt Gilman Camp-moc 9.5D",
        price=99.0, shipping=0.0, condition="Pre-owned", category_id=11450,
        item_specifics={
            "Brand": "Rancourt", "Model": "Rancourt Gilman Camp-moc",
            "US Shoe Size": "9.5",
        },
        url="", seller=None,
    )
    suggested = extract_search_query(listing)
    assert "9.5" not in suggested.query
    assert suggested.filters.get("shoe_size") == "9.5"


def test_extract_search_query_model_same_as_brand():
    """If Model is just the brand name, fall back to Brand + Style."""
    listing = ActiveListing(
        item_id="6", title="Rancourt Shoes",
        price=99.0, shipping=0.0, condition="Pre-owned", category_id=11450,
        item_specifics={
            "Brand": "Rancourt", "Model": "Rancourt",
            "Style": "Camp Moc",
        },
        url="", seller=None,
    )
    suggested = extract_search_query(listing)
    assert "Camp Moc" in suggested.query
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_scraper_active.py -v -k "model or generic_keyword or shoe_size"`

Expected: Multiple FAILs — `test_extract_search_query_uses_model_when_contains_brand` fails because "Gilman" is not in the query, etc.

---

### Task 2: Smarter Query Generation — Implementation

**Files:**
- Modify: `src/ebay_tracker/scraper.py:391-431` — `extract_search_query()`

- [ ] **Step 1: Rewrite `extract_search_query`**

Replace the `extract_search_query` function in `src/ebay_tracker/scraper.py` (starting at line 391) with:

```python
def extract_search_query(listing: ActiveListing) -> SuggestedQuery:
    specs = listing.item_specifics
    query_parts = []

    brand = specs.get("Brand")
    model = specs.get("Model")
    style = specs.get("Style")

    model_is_useful = model and model.strip().lower() != (brand or "").strip().lower()

    if model_is_useful:
        if brand and brand.lower() in model.lower():
            query_parts.append(model)
        elif brand:
            query_parts.append(brand)
            query_parts.append(model)
        else:
            query_parts.append(model)
    else:
        if brand:
            query_parts.append(brand)
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
    elif size and not specs.get("US Shoe Size"):
        query_parts.append(size)

    if not query_parts:
        query_parts = listing.title.split()[:6]

    filters = {}
    if listing.condition:
        filters["condition"] = listing.condition
    if listing.category_id:
        filters["category"] = listing.category_id

    shoe_size = specs.get("US Shoe Size")
    if shoe_size:
        filters["shoe_size"] = shoe_size

    return SuggestedQuery(
        query=" ".join(query_parts),
        filters=filters,
        raw_attributes=dict(specs),
    )
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/test_scraper_active.py -v`

Expected: All tests PASS, including the new Model-based tests and existing Levi's tests.

- [ ] **Step 3: Commit**

```bash
git add src/ebay_tracker/scraper.py tests/test_scraper_active.py
git commit -m "feat: smarter query generation — prefer Model over Style for specificity"
```

---

### Task 3: Comp Filtering — Tests

**Files:**
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write failing tests for brand filtering and outlier removal**

Add these tests to `tests/test_server.py`:

```python
from ebay_tracker.server import _filter_comps_by_brand, _remove_price_outliers


def _make_comp(title, price):
    return Listing(
        id=None, search_id=0, ebay_item_id="x",
        title=title, price=price, shipping=0.0,
        condition="Pre-owned", sold_date=date(2025, 1, 10),
        url=None, created_at=None,
    )


def test_filter_comps_by_brand_keeps_matches():
    comps = [
        _make_comp("Rancourt Gilman Camp Moc Brown", 110.0),
        _make_comp("Quoddy Blucher rancourt yuketen", 45.0),
        _make_comp("LL Bean Camp Moc Leather", 30.0),
        _make_comp("Rancourt & Co Ranger Moc", 150.0),
    ]
    filtered = _filter_comps_by_brand(comps, "Rancourt")
    assert len(filtered) == 3  # items 0, 1, 3 contain "rancourt"


def test_filter_comps_by_brand_case_insensitive():
    comps = [_make_comp("RANCOURT shoes", 100.0)]
    filtered = _filter_comps_by_brand(comps, "rancourt")
    assert len(filtered) == 1


def test_filter_comps_by_brand_empty_string_skips():
    comps = [_make_comp("Anything", 50.0)]
    filtered = _filter_comps_by_brand(comps, "")
    assert len(filtered) == 1


def test_remove_price_outliers_drops_extremes():
    comps = [
        _make_comp("A", 100.0),
        _make_comp("B", 110.0),
        _make_comp("C", 105.0),
        _make_comp("D", 95.0),
        _make_comp("E", 900.0),  # outlier
        _make_comp("F", 2.0),    # outlier
    ]
    filtered = _remove_price_outliers(comps)
    prices = [c.price for c in filtered]
    assert 900.0 not in prices
    assert 2.0 not in prices
    assert len(filtered) == 4


def test_remove_price_outliers_keeps_all_when_tight():
    comps = [_make_comp("A", p) for p in [100, 105, 110, 95, 108]]
    filtered = _remove_price_outliers(comps)
    assert len(filtered) == 5


def test_remove_price_outliers_needs_minimum_comps():
    """With fewer than 4 comps, don't remove outliers (not enough data)."""
    comps = [_make_comp("A", 100.0), _make_comp("B", 900.0)]
    filtered = _remove_price_outliers(comps)
    assert len(filtered) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_server.py -v -k "brand or outlier"`

Expected: ImportError — `_filter_comps_by_brand` and `_remove_price_outliers` don't exist yet.

---

### Task 4: Comp Filtering — Implementation

**Files:**
- Modify: `src/ebay_tracker/server.py`

- [ ] **Step 1: Add `_filter_comps_by_brand` and `_remove_price_outliers` functions**

Add these functions to `src/ebay_tracker/server.py`, before `_do_evaluate_listing`:

```python
def _filter_comps_by_brand(comps: list, brand: str) -> list:
    if not brand:
        return comps
    brand_lower = brand.lower()
    return [c for c in comps if brand_lower in c.title.lower()]


def _remove_price_outliers(comps: list) -> list:
    if len(comps) < 4:
        return comps
    prices = sorted(c.price for c in comps)
    q1 = prices[len(prices) // 4]
    q3 = prices[3 * len(prices) // 4]
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return [c for c in comps if lower <= c.price <= upper]
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/test_server.py -v -k "brand or outlier"`

Expected: All PASS.

- [ ] **Step 3: Commit**

```bash
git add src/ebay_tracker/server.py tests/test_server.py
git commit -m "feat: add comp brand filtering and IQR outlier removal"
```

---

### Task 5: Wire Filtering Into `_do_run_profit_analysis` and Add Response Enrichment

**Files:**
- Modify: `src/ebay_tracker/server.py` — `_do_run_profit_analysis()` and `run_profit_analysis()`

- [ ] **Step 1: Add `filter_brand` parameter and filtering logic to `_do_run_profit_analysis`**

Update the function signature to accept `filter_brand`:

```python
def _do_run_profit_analysis(
    listing_data: dict,
    comp_query: str,
    comp_filters: dict | None = None,
    fee_overrides: dict | None = None,
    threshold_overrides: dict | None = None,
    filter_brand: str = "",
) -> dict:
```

After the existing `comps = parse_listings(html, search_id=0)` line, add filtering and quality tracking:

```python
    comps_before_filter = len(comps)

    # Brand filtering
    if filter_brand:
        comps = _filter_comps_by_brand(comps, filter_brand)

    # Outlier removal
    comps = _remove_price_outliers(comps)
    comps_after_filter = len(comps)

    # Fallback: if filtering removed everything, use originals with warning
    all_comps = parse_listings(html, search_id=0)  # keep reference to originals
    quality_warning = None
    if not comps and comps_before_filter > 0:
        comps = all_comps
        comps_after_filter = len(comps)
        quality_warning = "All comps removed by filters, showing unfiltered results"
```

Wait — we shouldn't re-parse. Refactor to keep the original list. Replace the block after `comps = parse_listings(html, search_id=0)` with:

```python
    all_comps = comps
    comps_before_filter = len(all_comps)

    if filter_brand:
        comps = _filter_comps_by_brand(comps, filter_brand)
    comps = _remove_price_outliers(comps)
    comps_after_filter = len(comps)

    quality_warning = None
    if not comps and comps_before_filter > 0:
        comps = all_comps
        comps_after_filter = len(comps)
        quality_warning = "All comps removed by filters, showing unfiltered results"

    # Brand match rate (always computed from unfiltered for diagnostics)
    brand_from_listing = listing_data.get("item_specifics", {}).get("Brand", "")
    if brand_from_listing:
        brand_matches = sum(1 for c in all_comps if brand_from_listing.lower() in c.title.lower())
        brand_match_rate = round(brand_matches / len(all_comps) * 100, 1) if all_comps else 0
    else:
        brand_match_rate = None

    if brand_match_rate is not None and brand_match_rate < 50 and quality_warning is None:
        quality_warning = f"Only {brand_match_rate}% of comps match brand '{brand_from_listing}'"
```

- [ ] **Step 2: Add quality metadata to the output dict**

After the existing `output = { ... }` block, add:

```python
    output["comp_sample"] = [
        {"title": c.title, "price": c.price}
        for c in comps[:10]
    ]
    output["comps_before_filter"] = comps_before_filter
    output["comps_after_filter"] = comps_after_filter
    if brand_match_rate is not None:
        output["brand_match_rate"] = brand_match_rate
    if quality_warning:
        output["comp_quality_warning"] = quality_warning
```

- [ ] **Step 3: Add `filter_brand` parameter to the MCP tool function**

Update the `run_profit_analysis` async tool function signature:

```python
@mcp.tool()
async def run_profit_analysis(
    listing_data: str,
    comp_query: str,
    comp_filters: str = "{}",
    fee_overrides: str = "{}",
    threshold_overrides: str = "{}",
    filter_brand: str = "",
) -> str:
```

And pass it through to `_do_run_profit_analysis`:

```python
    result = await loop.run_in_executor(
        _playwright_executor,
        lambda: _do_run_profit_analysis(
            listing_data=parsed_listing,
            comp_query=comp_query,
            comp_filters=parsed_filters,
            fee_overrides=parsed_fees,
            threshold_overrides=parsed_thresholds,
            filter_brand=filter_brand,
        ),
    )
```

- [ ] **Step 4: Remove diagnostic logging**

Remove all `import sys, time as _time` and `print("[diag...")` lines from `server.py` and `browser.py`. These were added during debugging and should not ship.

- [ ] **Step 5: Update existing test for new output fields**

In `tests/test_server.py`, update `test_do_run_profit_analysis` to verify the new response fields:

After the existing assertions, add:

```python
    assert "comp_sample" in result
    assert len(result["comp_sample"]) <= 10
    assert "comps_before_filter" in result
    assert "comps_after_filter" in result
```

- [ ] **Step 6: Add integration test for filtering in `_do_run_profit_analysis`**

Add to `tests/test_server.py`:

```python
def test_do_run_profit_analysis_with_brand_filter():
    comps_data = [
        {"title": "Rancourt Gilman Camp Moc Brown", "price": 110.0,
         "ebay_item_id": "c1", "shipping": 0.0, "condition": "Pre-owned", "sold_date": "2025-01-05"},
        {"title": "Quoddy Blucher Moc", "price": 45.0,
         "ebay_item_id": "c2", "shipping": 0.0, "condition": "Pre-owned", "sold_date": "2025-01-10"},
        {"title": "Rancourt Ranger Moc Natural", "price": 150.0,
         "ebay_item_id": "c3", "shipping": 0.0, "condition": "Pre-owned", "sold_date": "2025-01-15"},
    ]
    listing_data = {
        "item_id": "999",
        "title": "Rancourt Gilman Camp-moc",
        "price": 99.0,
        "shipping": 27.76,
        "item_specifics": {"Brand": "Rancourt"},
        "url": "",
        "seller": "test",
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
            comp_query="Rancourt Camp Moc",
            filter_brand="Rancourt",
        )

    assert result["comps_before_filter"] == 3
    assert result["comps_after_filter"] == 2  # Quoddy filtered out
    assert result["comp_count"] == 2
```

- [ ] **Step 7: Run all tests**

Run: `python -m pytest tests/test_server.py tests/test_scraper_active.py -v`

Expected: All PASS.

- [ ] **Step 8: Commit**

```bash
git add src/ebay_tracker/server.py src/ebay_tracker/browser.py tests/test_server.py
git commit -m "feat: wire comp filtering into profit analysis with quality metadata"
```

---

### Task 6: Update `build_search_url` for Shoe Size Filter

**Files:**
- Modify: `src/ebay_tracker/scraper.py:35-85` — `build_search_url()`
- Modify: `tests/test_scraper.py` or `tests/test_scraper_active.py`

- [ ] **Step 1: Write failing test for shoe_size filter**

Add to `tests/test_scraper_active.py`:

```python
from ebay_tracker.scraper import build_search_url


def test_build_search_url_includes_shoe_size_aspect():
    url = build_search_url("Rancourt Gilman", {"category": 11450, "shoe_size": "9.5"})
    assert "US+Shoe+Size=9.5" in url or "US%20Shoe%20Size=9.5" in url
    assert "rt=nc" in url
    assert "LH_SpecificOnly=1" in url
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scraper_active.py::test_build_search_url_includes_shoe_size_aspect -v`

Expected: FAIL — shoe_size not handled.

- [ ] **Step 3: Add shoe_size handling to `build_search_url`**

In `src/ebay_tracker/scraper.py`, in the `build_search_url` function, add after the existing `size_type` block (around line 78):

```python
        if "shoe_size" in filters:
            shoe_size_val = filters["shoe_size"]
            params["US Shoe Size"] = shoe_size_val
            aspect_filters.append(True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_scraper_active.py -v`

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ebay_tracker/scraper.py tests/test_scraper_active.py
git commit -m "feat: support shoe_size aspect filter in search URL"
```

---

### Task 7: Copy Updated Files to Plugin Cache

**Files:**
- Source: `src/ebay_tracker/server.py`, `src/ebay_tracker/browser.py`, `src/ebay_tracker/scraper.py`
- Target: `~/.claude/plugins/cache/hurleysk-marketplace/ebay-resale/0.1.1/src/ebay_tracker/`

- [ ] **Step 1: Copy all modified source files to the plugin cache**

```powershell
$src = "C:\Users\shurley\source\repos\HurleySk\eBay-analysis-toolkit\src\ebay_tracker"
$dst = "C:\Users\shurley\.claude\plugins\cache\hurleysk-marketplace\ebay-resale\0.1.1\src\ebay_tracker"
Copy-Item "$src\server.py" "$dst\server.py" -Force
Copy-Item "$src\browser.py" "$dst\browser.py" -Force
Copy-Item "$src\scraper.py" "$dst\scraper.py" -Force
```

- [ ] **Step 2: Kill old server processes**

```powershell
Get-Process -Name python*, python3* -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'ebay_tracker' } |
    Stop-Process -Force -Confirm:$false
```

- [ ] **Step 3: Reconnect MCP server**

Run `/mcp` in Claude Code to reconnect the ebay-resale server with updated code.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: sync plugin cache with source"
```

Note: The plugin cache files are not tracked by git. This step is optional — only commit if the cache is in the repo.
