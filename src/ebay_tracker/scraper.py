import random
import re
import time
from datetime import date, datetime
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

from ebay_tracker.models import Listing


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def build_search_url(query: str, filters: dict | None = None, page: int = 1) -> str:
    """Build eBay sold listings search URL."""
    params = {
        "_nkw": query,
        "LH_Complete": "1",
        "LH_Sold": "1",
        "_ipg": "240",  # Max results per page
    }

    if page > 1:
        params["_pgn"] = str(page)

    if filters:
        if "max_price" in filters:
            params["_udhi"] = str(filters["max_price"])
        if "min_price" in filters:
            params["_udlo"] = str(filters["min_price"])
        if "condition" in filters:
            condition = filters["condition"].lower()
            if condition == "new":
                params["LH_ItemCondition"] = "1000"
            elif condition in ("pre-owned", "used"):
                params["LH_ItemCondition"] = "3000"

        # Category filter
        if "category" in filters:
            params["_sacat"] = str(filters["category"])

        # Aspect filters (color, size, inseam, size_type)
        aspect_filters = []
        if "color" in filters:
            params["Color"] = filters["color"]
            aspect_filters.append(True)
        if "size" in filters:
            params["Size"] = filters["size"]
            aspect_filters.append(True)
        if "inseam" in filters:
            params["Inseam"] = filters["inseam"]
            aspect_filters.append(True)
        if "size_type" in filters:
            params["Size Type"] = filters["size_type"]
            aspect_filters.append(True)

        # rt=nc is required when using aspect filters
        if aspect_filters:
            params["rt"] = "nc"

    return f"https://www.ebay.com/sch/i.html?{urlencode(params)}"


def get_headers() -> dict:
    """Get randomized browser-like headers."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


def fetch_page(url: str, proxy_url: str | None = None) -> str:
    """Fetch a page through the proxy."""
    transport = None
    if proxy_url:
        transport = httpx.HTTPTransport(proxy=proxy_url)

    with httpx.Client(transport=transport, timeout=30.0, follow_redirects=True) as client:
        response = client.get(url, headers=get_headers())
        response.raise_for_status()
        return response.text


def parse_listings(html: str, search_id: int) -> list[Listing]:
    """Parse eBay search results HTML and extract listings."""
    soup = BeautifulSoup(html, "lxml")
    listings = []

    # Try new s-card format first (2025+), then fall back to old s-item format
    items = soup.select("li.s-card")
    if items:
        listings = _parse_s_card_items(items, search_id)
    else:
        items = soup.select("li.s-item")
        listings = _parse_s_item_items(items, search_id)

    return listings


def _parse_s_card_items(items, search_id: int) -> list[Listing]:
    """Parse new eBay s-card format (2025+)."""
    listings = []

    for item in items:
        # Get item ID from data attribute
        item_id = item.get("data-listingid")
        if not item_id:
            continue

        # Extract title
        title_elem = item.select_one(".s-card__title")
        if not title_elem:
            continue
        title = title_elem.get_text(strip=True)

        # Extract URL
        link_elem = item.select_one("a[href*='/itm/']")
        url = link_elem.get("href") if link_elem else None

        # Extract price (s-card__price class)
        price_elem = item.select_one(".s-card__price")
        price_text = price_elem.get_text(strip=True) if price_elem else "0"
        price = parse_price(price_text)

        # Extract shipping - look for shipping-related text
        shipping = 0.0
        shipping_elem = item.select_one("[class*='shipping'], [class*='delivery']")
        if shipping_elem:
            shipping_text = shipping_elem.get_text(strip=True)
            shipping = parse_shipping(shipping_text)

        # Extract condition - often in a secondary info span
        condition = None
        condition_elem = item.select_one(".s-card__subtitle, .SECONDARY_INFO")
        if condition_elem:
            condition = condition_elem.get_text(strip=True)

        # Extract sold date - class "positive" often contains sold info
        sold_date = None
        # Look for text containing "Sold" or "Vendido" (Spanish/Portuguese)
        for elem in item.find_all(class_="positive"):
            text = elem.get_text(strip=True)
            if "sold" in text.lower() or "vendido" in text.lower():
                sold_date = parse_sold_date(text)
                break

        listings.append(Listing(
            id=None,
            search_id=search_id,
            ebay_item_id=item_id,
            title=title,
            price=price,
            shipping=shipping,
            condition=condition,
            sold_date=sold_date,
            url=url,
            created_at=None,
        ))

    return listings


def _parse_s_item_items(items, search_id: int) -> list[Listing]:
    """Parse old eBay s-item format (pre-2025)."""
    listings = []

    for item in items:
        # Skip "shop on eBay" promotional items
        title_elem = item.select_one(".s-item__title")
        if not title_elem:
            continue
        title = title_elem.get_text(strip=True)
        if title.lower() == "shop on ebay":
            continue

        # Extract URL and item ID
        link_elem = item.select_one("a.s-item__link")
        url = link_elem.get("href") if link_elem else None
        item_id = extract_item_id(url) if url else None
        if not item_id:
            continue

        # Extract price
        price_elem = item.select_one(".s-item__price")
        price_text = price_elem.get_text(strip=True) if price_elem else "0"
        price = parse_price(price_text)

        # Extract shipping
        shipping_elem = item.select_one(".s-item__shipping, .s-item__logisticsCost")
        shipping_text = shipping_elem.get_text(strip=True) if shipping_elem else "Free shipping"
        shipping = parse_shipping(shipping_text)

        # Extract condition
        condition_elem = item.select_one(".SECONDARY_INFO")
        condition = condition_elem.get_text(strip=True) if condition_elem else None

        # Extract sold date
        sold_elem = item.select_one(".POSITIVE")
        sold_text = sold_elem.get_text(strip=True) if sold_elem else None
        sold_date = parse_sold_date(sold_text) if sold_text else None

        listings.append(Listing(
            id=None,
            search_id=search_id,
            ebay_item_id=item_id,
            title=title,
            price=price,
            shipping=shipping,
            condition=condition,
            sold_date=sold_date,
            url=url,
            created_at=None,
        ))

    return listings


def extract_item_id(url: str) -> str | None:
    """Extract eBay item ID from URL."""
    if not url:
        return None
    match = re.search(r"/itm/(\d+)", url)
    return match.group(1) if match else None


def parse_price(text: str) -> float:
    """Parse price string to float."""
    # Remove currency symbol and commas
    cleaned = re.sub(r"[^\d.]", "", text)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_shipping(text: str) -> float:
    """Parse shipping cost string to float."""
    if "free" in text.lower():
        return 0.0
    return parse_price(text)


def parse_sold_date(text: str) -> date | None:
    """Parse sold date string to date object."""
    if not text:
        return None
    # Remove "Sold" prefix and extra whitespace
    cleaned = re.sub(r"^Sold\s+", "", text).strip()
    try:
        # Parse formats like "Jan 10, 2025"
        return datetime.strptime(cleaned, "%b %d, %Y").date()
    except ValueError:
        return None


def rate_limit_delay() -> None:
    """Random delay between requests to avoid detection."""
    time.sleep(random.uniform(2.0, 5.0))
