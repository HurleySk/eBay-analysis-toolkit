# eBay Tracker

Track eBay sold listings and analyze price trends to find the best deals.

## Features

- **Track searches** - Save eBay searches with custom filters
- **Fetch sold listings** - Scrape completed/sold listings via proxy
- **Price analysis** - Get median, range, and trend statistics
- **Deal recommendations** - Know what price is a "good deal" (bottom 20%)
- **Export to CSV** - Export data for further analysis

## Installation

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

```bash
# Clone and install
git clone <repo-url>
cd eBay-analysis-toolkit
uv sync
```

## Configuration

Create a `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

Configure your Decodo proxy for reliable eBay scraping:

```
# Use us.decodo.com for US geotargeting (avoids foreign language pages)
DECODO_PROXY_URL=http://username:password@us.decodo.com:10001

# Database location (optional, defaults to ./data/ebay_tracker.db)
EBAY_TRACKER_DB_PATH=./data/ebay_tracker.db
```

## Usage

### Add a search

```bash
# Basic search
ebay-tracker add "Levi's 501 32x30"

# With filters
ebay-tracker add "Levi's 501" \
  --category 11483 \
  --color Blue \
  --size 32 \
  --inseam 30 \
  --condition Pre-owned \
  --max-price 100

# With multiple colors (comma-separated)
ebay-tracker add "gitman vintage oxford" \
  --size Medium \
  --color "Blue,Pink,White"
```

### Fetch listings

```bash
# Fetch all searches (1 page each, ~240 items max)
ebay-tracker fetch

# Fetch specific search
ebay-tracker fetch "Levi's 501 32x30"

# Fetch multiple pages for more listings
ebay-tracker fetch "Levi's 501 32x30" --pages 5
```

Note: Each page contains up to 240 listings. Fetching >10 pages requires confirmation.

### Analyze prices

```bash
ebay-tracker analyze "Levi's 501 32x30"

# With target price
ebay-tracker analyze "Levi's 501 32x30" --target-price 40
```

Example output:
```
Levi's 501 32x30 (47 sales tracked)

Price:      $42 median  |  $15-89 range  |  $44 avg
Frequency:  ~1 listing every 2 days
Trend:      Stable

Recommendation: A price under $35 is a good deal (bottom 20%)
Target $40: ~45th percentile, expected wait ~4 days
```

### View history

```bash
ebay-tracker history "Levi's 501 32x30"
ebay-tracker history "Levi's 501 32x30" --limit 50
```

### Export to CSV

```bash
# To stdout
ebay-tracker export "Levi's 501 32x30"

# To file
ebay-tracker export "Levi's 501 32x30" -o listings.csv
```

### Edit a search

```bash
# Add/update filters
ebay-tracker edit "Levi's 501" --color Black --inseam 32

# Clear all filters
ebay-tracker edit "Levi's 501" --clear-filters
```

### Other commands

```bash
# List all searches
ebay-tracker list

# Remove a search
ebay-tracker remove "Levi's 501 32x30"

# Check status
ebay-tracker status
```

## Filter Options

| Option | Description | Example |
|--------|-------------|---------|
| `--condition` | Item condition | `Pre-owned`, `New` |
| `--min-price` | Minimum price | `20` |
| `--max-price` | Maximum price | `100` |
| `--category` | eBay category ID | `11483` (Men's Jeans) |
| `--color` | Color filter (comma-separated for multiple) | `Blue` or `Blue,Pink,White` |
| `--size` | Size filter (comma-separated for multiple) | `32` or `S,M,L` |
| `--inseam` | Inseam length (comma-separated for multiple) | `30` or `30,32` |
| `--size-type` | Size type | `Regular`, `Big & Tall` |

### Common Category IDs

| Category | ID |
|----------|-----|
| Men's Jeans | 11483 |
| Men's Pants | 11484 |
| Men's T-Shirts | 15687 |
| Men's Coats & Jackets | 57988 |
| Women's Clothing | 11450 |

## Development

```bash
# Run tests
uv run pytest -v

# Run linter
uv run ruff check src tests

# Run with auto-fix
uv run ruff check --fix src tests
```

## How It Works

1. **Scraping**: Fetches eBay's completed/sold listings page using a residential proxy
2. **Parsing**: Extracts item details (title, price, shipping, condition, sold date)
3. **Storage**: Saves listings to SQLite with deduplication by eBay item ID
4. **Analysis**: Calculates statistics and identifies good deal thresholds

The tool only scrapes historical sold listings (via `LH_Complete=1&LH_Sold=1` parameters), giving you real market data on what items actually sell for.
