import random
import re
import time
from datetime import date, datetime
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

from ebay_tracker.browser import BrowserFetcher
from ebay_tracker.models import Listing, ActiveListing, SuggestedQuery


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


_browser_fetcher: BrowserFetcher | None = None


def _get_browser_fetcher(proxy_url: str | None) -> BrowserFetcher:
    global _browser_fetcher
    if _browser_fetcher is None or _browser_fetcher._proxy_url != proxy_url:
        if _browser_fetcher is not None:
            _browser_fetcher.stop()
        _browser_fetcher = BrowserFetcher(proxy_url)
    return _browser_fetcher


def build_search_url(query: str, filters: dict | None = None) -> str:
    """Build eBay sold listings search URL."""
    params = {
        "_nkw": query,
        "LH_Complete": "1",
        "LH_Sold": "1",
        "_ipg": "240",  # Max results per page
    }

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
        # These can be single values or lists for multiple values
        aspect_filters = []
        if "color" in filters:
            color_val = filters["color"]
            params["Color"] = "|".join(color_val) if isinstance(color_val, list) else color_val
            aspect_filters.append(True)
        if "size" in filters:
            size_val = filters["size"]
            params["Size"] = "|".join(size_val) if isinstance(size_val, list) else size_val
            aspect_filters.append(True)
        if "inseam" in filters:
            inseam_val = filters["inseam"]
            params["Inseam"] = "|".join(inseam_val) if isinstance(inseam_val, list) else inseam_val
            aspect_filters.append(True)
        if "size_type" in filters:
            size_type_val = filters["size_type"]
            params["Size Type"] = "|".join(size_type_val) if isinstance(size_type_val, list) else size_type_val
            aspect_filters.append(True)
        if "shoe_size" in filters:
            params["US Shoe Size"] = filters["shoe_size"]
            aspect_filters.append(True)

        # rt=nc and LH_SpecificOnly are required for aspect filters to be enforced
        if aspect_filters:
            params["rt"] = "nc"
            params["LH_SpecificOnly"] = "1"

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


_EBAY_CONTENT_SELECTOR = "li.s-card, li.s-item, h1.x-item-title__mainTitle"


def fetch_page(url: str, proxy_url: str | None = None, use_browser: bool = False) -> str:
    """Fetch a page. use_browser=True for Playwright (sold listings, item pages)."""
    if use_browser:
        fetcher = _get_browser_fetcher(proxy_url)
        selector = _EBAY_CONTENT_SELECTOR if "ebay.com" in url else None
        return fetcher.fetch(url, wait_selector=selector)

    try:
        from curl_cffi import requests as cffi_requests
        response = cffi_requests.get(
            url,
            headers=get_headers(),
            proxy=proxy_url,
            impersonate="chrome",
            timeout=30,
            allow_redirects=True,
        )
        response.raise_for_status()
        return response.text
    except ImportError:
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

        # Skip "Shop on eBay" promotional items
        if title.lower() == "shop on ebay":
            continue

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
    """Parse price string to float. For price ranges, takes the lower bound."""
    prices = re.findall(r"\d[\d,]*\.?\d*", text)
    if not prices:
        return 0.0
    cleaned = prices[0].replace(",", "")
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
    html = fetch_page(url, proxy_url, use_browser=True)
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
