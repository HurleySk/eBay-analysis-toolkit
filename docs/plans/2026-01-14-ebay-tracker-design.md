# eBay Sold Listings Analyzer — Design Document

## Overview

A Python CLI tool that scrapes eBay completed listings, stores them in SQLite, and provides price/availability predictions to help make patient buying decisions.

**Primary use case:** Track specific clothing items (e.g., "Levi's 501 32x30 dark wash"), analyze historical sold prices, and predict how long to wait for a target price.

**Core workflow:**

```
$ ebay-tracker add "Levi's 501 32x30 dark wash"
$ ebay-tracker fetch
$ ebay-tracker analyze "Levi's 501 32x30"
```

**Example output:**

```
Levi's 501 32x30 dark wash (47 sales tracked)

Price:      $38 median  |  $28-55 range  |  $42 avg
Frequency:  ~1 listing every 8 days
Trend:      Stable (no significant change last 90 days)

Recommendation: A price under $32 is a good deal (bottom 20%)
                Expected wait: ~40 days for a sub-$32 listing
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  CLI Layer (typer)                                  │
│  Commands: add, fetch, analyze, list, remove, etc. │
└─────────────────────────────────────────────────────┘
                        │
┌─────────────────────────────────────────────────────┐
│  Core Services                                      │
│  ┌─────────────┐ ┌─────────────┐ ┌───────────────┐ │
│  │  Scraper    │ │  Analyzer   │ │  Storage      │ │
│  │  (httpx +   │ │  (pandas +  │ │  (SQLite +    │ │
│  │  bs4/lxml)  │ │  stats)     │ │  raw SQL)     │ │
│  └─────────────┘ └─────────────┘ └───────────────┘ │
└─────────────────────────────────────────────────────┘
                        │
┌─────────────────────────────────────────────────────┐
│  Infrastructure                                     │
│  ┌─────────────┐ ┌─────────────┐                   │
│  │  Decodo     │ │  Config     │                   │
│  │  Proxy      │ │  (.env)     │                   │
│  └─────────────┘ └─────────────┘                   │
└─────────────────────────────────────────────────────┘
```

**Key design decisions:**

- **No ORM** — Raw SQL with simple helper functions keeps it lean and transparent
- **Scraper is swappable** — If HTML parsing breaks, Playwright can be swapped in without touching other code
- **Analyzer is pure functions** — Takes data in, returns stats; easy to test and extend
- **Decodo proxy from the start** — All requests routed through proxy to avoid IP blocks

## Data Model

```sql
-- Searches you're tracking
CREATE TABLE searches (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,           -- Display name
    query           TEXT NOT NULL,           -- eBay search query
    filters         TEXT,                    -- JSON: condition, size, min/max price
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_fetched_at TIMESTAMP
);

-- Individual sold listings
CREATE TABLE listings (
    id              INTEGER PRIMARY KEY,
    search_id       INTEGER NOT NULL REFERENCES searches(id),
    ebay_item_id    TEXT NOT NULL,           -- For deduplication
    title           TEXT NOT NULL,
    price           REAL NOT NULL,           -- Sold price (USD)
    shipping        REAL,                    -- Shipping cost
    condition       TEXT,
    sold_date       DATE,
    url             TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(search_id, ebay_item_id)
);

-- Track fetch history
CREATE TABLE fetch_log (
    id              INTEGER PRIMARY KEY,
    search_id       INTEGER NOT NULL REFERENCES searches(id),
    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    listings_found  INTEGER,
    status          TEXT                     -- "success", "blocked", "error"
);
```

## CLI Commands

### Managing searches

| Command | Description |
|---------|-------------|
| `add <name>` | Add a search to track |
| `list` | Show all tracked searches with stats |
| `remove <name>` | Remove a search and its listings |
| `edit <name>` | Modify search query or filters |

```bash
$ ebay-tracker add "Levi's 501 32x30" --condition "Pre-owned" --max-price 100
$ ebay-tracker list
$ ebay-tracker remove "Levi's 501 32x30"
```

### Fetching data

| Command | Description |
|---------|-------------|
| `fetch` | Fetch new listings for all searches |
| `fetch <name>` | Fetch for a specific search |
| `fetch --days 90` | How far back to look (default: 90) |

```bash
$ ebay-tracker fetch
$ ebay-tracker fetch "Levi's 501 32x30"
```

### Analysis

| Command | Description |
|---------|-------------|
| `analyze <name>` | Price stats and predictions |
| `analyze <name> --target-price 35` | Wait time for target price |
| `history <name>` | Show all recorded sales |
| `export <name>` | Dump to CSV |

```bash
$ ebay-tracker analyze "Levi's 501 32x30"
$ ebay-tracker analyze "Levi's 501 32x30" --target-price 35
$ ebay-tracker history "Levi's 501 32x30" --limit 20
$ ebay-tracker export "Levi's 501 32x30" -o sales.csv
```

### Utility

| Command | Description |
|---------|-------------|
| `config` | Show/set configuration |
| `status` | Check proxy, last fetch times |

## Analysis & Predictions

### Phase 1: Simple statistics

```python
{
    "count": 47,
    "price": {
        "median": 38.00,
        "mean": 42.15,
        "min": 22.00,
        "max": 78.00,
        "std_dev": 12.30,
        "percentiles": {"p20": 32.00, "p50": 38.00, "p80": 52.00}
    },
    "frequency": {
        "avg_days_between": 8.2,
        "listings_per_month": 3.7
    },
    "trend": "stable"
}
```

### Prediction logic

For "how long until price X?":
1. Calculate what percentile the target price is (e.g., $32 = 20th percentile)
2. Expected wait = `avg_days_between / (percentile / 100)`
3. Example: 8 days avg / 0.20 = ~40 days expected wait

### Future enhancements (designed for, not built)

- Seasonal patterns
- Day-of-week patterns
- Condition-based pricing analysis
- Trend extrapolation

## Scraping Strategy

### Target URL

```
https://www.ebay.com/sch/i.html?_nkw=<query>&LH_Complete=1&LH_Sold=1&_ipg=240
```

### Request flow

All requests routed through Decodo proxy from the start.

### Anti-detection measures

1. Rotating user agents (random browser UA per request)
2. Rate limiting (2-5 second random delay between requests)
3. Browser-like headers (Accept, Accept-Language, etc.)

### HTML parsing targets

```
<li class="s-item">
  ├── item ID (from data attribute or URL)
  ├── title (.s-item__title)
  ├── price (.s-item__price)
  ├── shipping (.s-item__shipping)
  ├── condition (.SECONDARY_INFO)
  └── sold date (.POSITIVE)
</li>
```

### Fallback plan

If HTML scraping breaks, swap in Playwright with headless browser through same proxy.

## Project Structure

```
ebay-tracker/
├── pyproject.toml
├── .env                     # Decodo credentials (gitignored)
├── .env.example
├── README.md
├── src/
│   └── ebay_tracker/
│       ├── __init__.py
│       ├── cli.py           # Typer commands
│       ├── config.py        # Settings, env vars
│       ├── db.py            # SQLite setup, queries
│       ├── scraper.py       # HTTP requests, parsing
│       ├── analyzer.py      # Stats, predictions
│       └── models.py        # Dataclasses
├── tests/
│   ├── test_scraper.py
│   ├── test_analyzer.py
│   └── fixtures/            # Sample HTML for testing
└── data/
    └── ebay_tracker.db      # SQLite database (gitignored)
```

## Dependencies

```toml
[project]
dependencies = [
    "typer",
    "httpx",
    "beautifulsoup4",
    "lxml",
    "pandas",
    "rich",
    "python-dotenv",
]

[project.optional-dependencies]
browser = ["playwright"]
dev = ["pytest", "ruff"]
```

## Configuration

Environment variables (`.env`):

```
DECODO_PROXY_URL=http://user:pass@proxy.decodo.com:port
EBAY_TRACKER_DB_PATH=./data/ebay_tracker.db
```
