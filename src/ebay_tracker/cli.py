import csv
from io import StringIO
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ebay_tracker.analyzer import analyze_listings, get_recommendation
from ebay_tracker.categories import get_categories_for_preference, search_categories
from ebay_tracker.config import (
    FeeConfig, ThresholdConfig, get_config, get_user_prefs, save_user_prefs,
)
from ebay_tracker.db import Database
from ebay_tracker.evaluator import run_profit_analysis
from ebay_tracker.models import Search, FetchLog
from ebay_tracker.scraper import (
    build_search_url, fetch_page, parse_listings,
    fetch_active_listing, extract_search_query, rate_limit_delay,
)

app = typer.Typer(
    name="ebay-tracker",
    help="Track eBay sold listings and predict prices",
    no_args_is_help=True,
)
console = Console()


def get_db() -> Database:
    """Get database connection."""
    config = get_config()
    db = Database(config.db_path)
    db.init()
    return db


def parse_multi_value(value: str | None) -> str | list[str] | None:
    """Parse comma-separated values into a list, or return single value."""
    if value is None:
        return None
    if "," in value:
        return [v.strip() for v in value.split(",")]
    return value


def prompt_gender_preference() -> str:
    """Prompt user for gender preference and save to config."""
    console.print("\n[cyan]Which categories interest you?[/cyan]")
    console.print("  [1] Men's clothing")
    console.print("  [2] Women's clothing")
    console.print("  [3] Both")

    while True:
        choice = typer.prompt("Select", default="1")
        if choice in ("1", "2", "3"):
            break
        console.print("[red]Invalid selection. Enter 1, 2, or 3.[/red]")

    pref = {"1": "mens", "2": "womens", "3": "both"}[choice]
    prefs = get_user_prefs()
    prefs.gender_preference = pref
    save_user_prefs(prefs)
    console.print("[green]Preference saved.[/green]")
    return pref


def prompt_category_selection(gender_pref: str) -> int:
    """Interactive category selection with search."""
    categories = get_categories_for_preference(gender_pref)

    while True:
        console.print("\n[cyan]Size/color filters require a category. Search or select:[/cyan]")
        cat_list = list(categories.items())
        for i, (cat_id, name) in enumerate(cat_list, 1):
            console.print(f"  [{i}] {name} ({cat_id})")
        console.print("  [s] Search categories")
        console.print("  [m] Enter ID manually")

        choice = typer.prompt("Select")

        if choice.lower() == "s":
            query = typer.prompt("Search")
            results = search_categories(query, gender_pref)
            if results:
                categories = results
                console.print(f"[dim]Found {len(results)} matches[/dim]")
            else:
                console.print("[yellow]No matches. Showing full list.[/yellow]")
                categories = get_categories_for_preference(gender_pref)
        elif choice.lower() == "m":
            cat_id = typer.prompt("Category ID", type=int)
            return cat_id
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(cat_list):
                return cat_list[idx][0]
            console.print("[red]Invalid selection[/red]")
        else:
            console.print("[red]Invalid input[/red]")


@app.command()
def add(
    name: str = typer.Argument(..., help="Name for this search"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="eBay search query (defaults to name)"),
    condition: Optional[str] = typer.Option(None, "--condition", "-c", help="Item condition filter"),
    min_price: Optional[float] = typer.Option(None, "--min-price", help="Minimum price filter"),
    max_price: Optional[float] = typer.Option(None, "--max-price", help="Maximum price filter"),
    category: Optional[int] = typer.Option(None, "--category", "-cat", help="eBay category ID (e.g., 11483 for Men's Jeans)"),
    color: Optional[str] = typer.Option(None, "--color", help="Color filter (comma-separated for multiple: Blue,Pink,White)"),
    size: Optional[str] = typer.Option(None, "--size", help="Size filter (comma-separated for multiple: S,M,L)"),
    inseam: Optional[str] = typer.Option(None, "--inseam", help="Inseam length (comma-separated for multiple: 30,32)"),
    size_type: Optional[str] = typer.Option(None, "--size-type", help="Size type (Regular, Big & Tall)"),
):
    """Add a new search to track."""
    db = get_db()

    # Check if already exists
    if db.get_search_by_name(name):
        console.print(f"[red]Search '{name}' already exists[/red]")
        raise typer.Exit(1)

    # Build filters
    filters = {}
    if condition:
        filters["condition"] = condition
    if min_price is not None:
        filters["min_price"] = min_price
    if max_price is not None:
        filters["max_price"] = max_price
    if category is not None:
        filters["category"] = category
    if color:
        filters["color"] = parse_multi_value(color)
    if size:
        filters["size"] = parse_multi_value(size)
    if inseam:
        filters["inseam"] = parse_multi_value(inseam)
    if size_type:
        filters["size_type"] = parse_multi_value(size_type)

    # Check if aspect filters are used without a category - prompt wizard
    aspect_filters_used = any(filters.get(f) for f in ["color", "size", "inseam", "size_type"])
    if aspect_filters_used and not category:
        prefs = get_user_prefs()
        if not prefs.gender_preference:
            prefs.gender_preference = prompt_gender_preference()

        selected_category = prompt_category_selection(prefs.gender_preference)
        filters["category"] = selected_category

    search = Search(
        id=None,
        name=name,
        query=query or name,
        filters=filters if filters else None,
        created_at=None,
        last_fetched_at=None,
    )

    db.add_search(search)
    db.close()

    console.print(f"[green]Added search:[/green] {name}")
    if filters:
        console.print(f"  Filters: {filters}")


@app.command("list")
def list_searches():
    """List all tracked searches."""
    db = get_db()
    searches = db.get_all_searches()

    if not searches:
        console.print("[dim]No searches tracked yet. Use 'add' to create one.[/dim]")
        db.close()
        return

    table = Table(title="Tracked Searches")
    table.add_column("Name", style="cyan")
    table.add_column("Query", style="dim")
    table.add_column("Listings", justify="right")
    table.add_column("Last Fetched", style="dim")

    for search in searches:
        count = db.get_listing_count_for_search(search.id)
        last_fetched = search.last_fetched_at.strftime("%Y-%m-%d %H:%M") if search.last_fetched_at else "Never"
        table.add_row(
            search.name,
            search.query if search.query != search.name else "-",
            str(count),
            last_fetched,
        )

    console.print(table)
    db.close()


@app.command()
def remove(
    name: str = typer.Argument(..., help="Name of search to remove"),
):
    """Remove a search and all its listings."""
    db = get_db()

    search = db.get_search_by_name(name)
    if not search:
        console.print(f"[red]Search '{name}' not found[/red]")
        db.close()
        raise typer.Exit(1)

    listing_count = db.get_listing_count_for_search(search.id)
    db.delete_search(search.id)
    db.close()

    console.print(f"[green]Removed search:[/green] {name}")
    if listing_count > 0:
        console.print(f"  [dim]Deleted {listing_count} listings[/dim]")


@app.command()
def edit(
    name: str = typer.Argument(..., help="Name of search to edit"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="New search query"),
    condition: Optional[str] = typer.Option(None, "--condition", "-c", help="Item condition filter"),
    min_price: Optional[float] = typer.Option(None, "--min-price", help="Minimum price filter"),
    max_price: Optional[float] = typer.Option(None, "--max-price", help="Maximum price filter"),
    category: Optional[int] = typer.Option(None, "--category", "-cat", help="eBay category ID"),
    color: Optional[str] = typer.Option(None, "--color", help="Color filter (comma-separated for multiple)"),
    size: Optional[str] = typer.Option(None, "--size", help="Size filter (comma-separated for multiple)"),
    inseam: Optional[str] = typer.Option(None, "--inseam", help="Inseam length (comma-separated for multiple)"),
    size_type: Optional[str] = typer.Option(None, "--size-type", help="Size type"),
    clear_filters: bool = typer.Option(False, "--clear-filters", help="Remove all filters"),
):
    """Edit an existing search's query or filters."""
    db = get_db()

    search = db.get_search_by_name(name)
    if not search:
        console.print(f"[red]Search '{name}' not found[/red]")
        db.close()
        raise typer.Exit(1)

    # Handle clear filters
    if clear_filters:
        db.update_search(search.id, filters={})
        db.close()
        console.print(f"[green]Cleared all filters for:[/green] {name}")
        return

    # Build updated filters (merge with existing)
    new_filters = search.filters.copy() if search.filters else {}

    if condition is not None:
        new_filters["condition"] = condition
    if min_price is not None:
        new_filters["min_price"] = min_price
    if max_price is not None:
        new_filters["max_price"] = max_price
    if category is not None:
        new_filters["category"] = category
    if color is not None:
        new_filters["color"] = parse_multi_value(color)
    if size is not None:
        new_filters["size"] = parse_multi_value(size)
    if inseam is not None:
        new_filters["inseam"] = parse_multi_value(inseam)
    if size_type is not None:
        new_filters["size_type"] = parse_multi_value(size_type)

    # Check if aspect filters are used without a category - prompt wizard
    aspect_filters_used = any(new_filters.get(f) for f in ["color", "size", "inseam", "size_type"])
    if aspect_filters_used and not new_filters.get("category"):
        prefs = get_user_prefs()
        if not prefs.gender_preference:
            prefs.gender_preference = prompt_gender_preference()

        selected_category = prompt_category_selection(prefs.gender_preference)
        new_filters["category"] = selected_category

    # Check if anything changed
    filters_changed = new_filters != (search.filters or {})
    query_changed = query is not None and query != search.query

    if not filters_changed and not query_changed:
        console.print("[yellow]No changes specified[/yellow]")
        db.close()
        return

    # Apply updates
    db.update_search(
        search.id,
        query=query if query_changed else None,
        filters=new_filters if filters_changed else None,
    )
    db.close()

    console.print(f"[green]Updated search:[/green] {name}")
    if query_changed:
        console.print(f"  Query: {query}")
    if filters_changed:
        console.print(f"  Filters: {new_filters}")


@app.command()
def status():
    """Show status of proxy and database."""
    config = get_config()

    console.print("[bold]eBay Tracker Status[/bold]")
    console.print()

    # Database status
    console.print(f"[cyan]Database:[/cyan] {config.db_path}")
    if config.db_path.exists():
        db = get_db()
        searches = db.get_all_searches()
        total_listings = sum(db.get_listing_count_for_search(s.id) for s in searches)
        console.print(f"  Searches: {len(searches)}")
        console.print(f"  Listings: {total_listings}")
        db.close()
    else:
        console.print("  [dim]Not initialized[/dim]")

    console.print()

    # Proxy status
    console.print("[cyan]Proxy:[/cyan]", end=" ")
    if config.proxy_url:
        # Mask credentials in URL
        masked = config.proxy_url.split("@")[-1] if "@" in config.proxy_url else config.proxy_url
        console.print(f"Configured ({masked})")
    else:
        console.print("[yellow]Not configured[/yellow]")
        console.print("  [dim]Set DECODO_PROXY_URL in .env[/dim]")


@app.command()
def fetch(
    name: Optional[str] = typer.Argument(None, help="Name of search to fetch (all if not specified)"),
):
    """Fetch new listings from eBay."""
    config = get_config()
    db = get_db()

    if name:
        search = db.get_search_by_name(name)
        if not search:
            console.print(f"[red]Search '{name}' not found[/red]")
            db.close()
            raise typer.Exit(1)
        searches = [search]
    else:
        searches = db.get_all_searches()

    if not searches:
        console.print("[dim]No searches to fetch. Use 'add' to create one.[/dim]")
        db.close()
        return

    if not config.proxy_url:
        console.print("[yellow]Warning: No proxy configured. Requests may be blocked.[/yellow]")
        console.print("[dim]Set DECODO_PROXY_URL in .env for better reliability.[/dim]")
        console.print()

    total_new = 0

    for search in searches:
        console.print(f"[cyan]Fetching:[/cyan] {search.name}")

        try:
            url = build_search_url(search.query, search.filters)
            html = fetch_page(url, config.proxy_url, use_browser=True)
            listings = parse_listings(html, search.id)

            new_count = 0
            for listing in listings:
                if db.add_listing(listing):
                    new_count += 1

            db.update_search_last_fetched(search.id)
            db.add_fetch_log(FetchLog(
                id=None,
                search_id=search.id,
                fetched_at=None,
                listings_found=len(listings),
                status="success",
            ))

            console.print(f"  Found {len(listings)} listings, {new_count} new")
            total_new += new_count

        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")
            db.add_fetch_log(FetchLog(
                id=None,
                search_id=search.id,
                fetched_at=None,
                listings_found=0,
                status=f"error: {e}",
            ))

        # Rate limit between searches
        if len(searches) > 1 and search != searches[-1]:
            rate_limit_delay()

    console.print()
    console.print(f"[green]Done![/green] {total_new} new listings added")
    db.close()


@app.command()
def analyze(
    name: str = typer.Argument(..., help="Name of search to analyze"),
    target_price: Optional[float] = typer.Option(None, "--target-price", "-t", help="Target price for wait estimate"),
):
    """Analyze price statistics and get predictions."""
    db = get_db()

    search = db.get_search_by_name(name)
    if not search:
        console.print(f"[red]Search '{name}' not found[/red]")
        db.close()
        raise typer.Exit(1)

    listings = db.get_listings_for_search(search.id)

    if not listings:
        console.print(f"[yellow]{search.name}[/yellow] - No data")
        console.print("[dim]Run 'fetch' to collect listings first.[/dim]")
        db.close()
        return

    stats = analyze_listings(listings)
    rec = get_recommendation(listings, target_price)

    # Header
    console.print()
    console.print(f"[bold cyan]{search.name}[/bold cyan] ({stats['count']} sales tracked)")
    console.print()

    # Price stats
    price = stats["price"]
    console.print(
        f"[bold]Price:[/bold]      "
        f"${price['median']:.0f} median  |  "
        f"${price['min']:.0f}-{price['max']:.0f} range  |  "
        f"${price['mean']:.0f} avg"
    )

    # Frequency
    freq = stats["frequency"]
    if freq["avg_days_between"]:
        console.print(
            f"[bold]Frequency:[/bold]  "
            f"~1 listing every {freq['avg_days_between']:.0f} days"
        )

    # Trend
    console.print(f"[bold]Trend:[/bold]      {stats['trend'].capitalize()}")
    console.print()

    # Recommendation
    if rec.get("good_deal_threshold"):
        console.print(
            f"[green]Recommendation:[/green] A price under "
            f"${rec['good_deal_threshold']:.0f} is a good deal (bottom 20%)"
        )

    # Target price prediction
    if target_price and rec.get("expected_wait_days"):
        console.print(
            f"[green]Target ${target_price:.0f}:[/green] "
            f"~{rec['target_percentile']:.0f}th percentile, "
            f"expected wait ~{rec['expected_wait_days']:.0f} days"
        )

    db.close()


@app.command()
def history(
    name: str = typer.Argument(..., help="Name of search to show history for"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of listings to show"),
):
    """Show listing history for a search."""
    db = get_db()

    search = db.get_search_by_name(name)
    if not search:
        console.print(f"[red]Search '{name}' not found[/red]")
        db.close()
        raise typer.Exit(1)

    listings = db.get_listings_for_search(search.id)

    if not listings:
        console.print(f"[yellow]{search.name}[/yellow] - No listings")
        console.print("[dim]Run 'fetch' to collect listings first.[/dim]")
        db.close()
        return

    table = Table(title=f"Recent Sales: {search.name}")
    table.add_column("Date", style="dim")
    table.add_column("Title")
    table.add_column("Price", justify="right", style="green")
    table.add_column("Ship", justify="right", style="dim")
    table.add_column("Condition", style="dim")
    table.add_column("URL", style="dim")

    for listing in listings[:limit]:
        date_str = listing.sold_date.strftime("%Y-%m-%d") if listing.sold_date else "-"
        shipping = f"${listing.shipping:.2f}" if listing.shipping else "Free"

        table.add_row(
            date_str,
            listing.title,
            f"${listing.price:.2f}",
            shipping,
            listing.condition or "-",
            listing.url or "-",
        )

    console.print(table)

    if len(listings) > limit:
        console.print(f"[dim]Showing {limit} of {len(listings)} listings. Use --limit to see more.[/dim]")

    db.close()


@app.command()
def export(
    name: str = typer.Argument(..., help="Name of search to export"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path (default: stdout)"),
):
    """Export listings to CSV."""
    db = get_db()

    search = db.get_search_by_name(name)
    if not search:
        console.print(f"[red]Search '{name}' not found[/red]")
        db.close()
        raise typer.Exit(1)

    listings = db.get_listings_for_search(search.id)

    if not listings:
        console.print(f"[yellow]{search.name}[/yellow] - No listings to export")
        db.close()
        return

    # Build CSV
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "title", "price", "shipping", "total", "condition", "url", "ebay_item_id"])

    for listing in listings:
        writer.writerow([
            listing.sold_date.isoformat() if listing.sold_date else "",
            listing.title,
            listing.price,
            listing.shipping or 0,
            listing.total_price,
            listing.condition or "",
            listing.url or "",
            listing.ebay_item_id,
        ])

    csv_content = buffer.getvalue()

    if output:
        output.write_text(csv_content)
        console.print(f"[green]Exported {len(listings)} listings to {output}[/green]")
    else:
        print(csv_content)

    db.close()


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
        buyer_tax_rate=prefs.fees.buyer_tax_rate,
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
        html = fetch_page(url, config.proxy_url, use_browser=True)
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
    result_table.add_row("Per-order Fee", f"-${result.net_proceeds.payment_processing_fee:.2f}")
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
    result_table.add_row(
        f"[{verdict_style}]Verdict[/{verdict_style}]",
        f"[{verdict_style}]{verdict_text}[/{verdict_style}]",
    )

    console.print(result_table)

    if export_path:
        export_data = {
            "listing": {
                "item_id": active.item_id, "title": active.title,
                "price": active.price, "shipping": active.shipping,
                "condition": active.condition, "url": active.url,
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
                "confidence": result.confidence, "comp_count": result.comp_count,
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


if __name__ == "__main__":
    app()


# --- Opportunity scanning ---

DEFAULT_SEEDS = Path("seeds/menswear.toml")
MAX_CONSECUTIVE_EMPTY = 3


def _live_fetch(proxy_url: str | None):
    """Rate-limited browser fetch with images/fonts blocked (proxy bandwidth is metered)."""
    def fetch(url: str) -> str:
        rate_limit_delay()
        return fetch_page(url, proxy_url, use_browser=True, block_resources=True)
    return fetch


def _scan_fetcher(cache_dir: Path):
    from ebay_tracker.screener import cached_fetch

    config = get_config()
    if not config.proxy_url:
        console.print("[yellow]Warning: No proxy configured. Requests may be blocked.[/yellow]")
    return cached_fetch(_live_fetch(config.proxy_url), cache_dir)


def _fee_and_thresholds() -> tuple[FeeConfig, ThresholdConfig]:
    prefs = get_user_prefs()
    return prefs.fees, prefs.thresholds


def _money(value: float | None) -> str:
    return "-" if value is None else f"${value:,.0f}"


@app.command("scan-niches")
def scan_niches(
    seeds_path: Path = typer.Option(DEFAULT_SEEDS, "--seeds", help="Seed niches TOML file"),
    only: Optional[str] = typer.Option(None, "--only", help="Comma-separated seed names to run"),
    limit: Optional[int] = typer.Option(None, "--limit", help="Run only the first N seeds"),
    out: Optional[Path] = typer.Option(None, "--out", help="JSON output path"),
    cache_dir: Optional[Path] = typer.Option(None, "--cache-dir", help="HTML cache directory"),
):
    """Rank seed niches by how ripe eBay-to-eBay flips are (sell-through, spread, margin)."""
    import json as json_mod
    from dataclasses import asdict

    from ebay_tracker.screener import Gates, default_cache_dir, load_seeds, rank, screen_niche

    seeds = load_seeds(seeds_path)
    if only:
        wanted = {n.strip().lower() for n in only.split(",")}
        seeds = [s for s in seeds if s.name.lower() in wanted]
    if limit:
        seeds = seeds[:limit]
    cache_dir = cache_dir or default_cache_dir()
    out = out or cache_dir / "niches.json"
    fee_cfg, thresholds = _fee_and_thresholds()
    gates = Gates()
    fetch, counters = _scan_fetcher(cache_dir / "html")

    results, errors, empty_streak = [], [], 0
    for i, seed in enumerate(seeds, 1):
        console.print(f"[cyan]{i}/{len(seeds)}[/cyan] {seed.name}")
        try:
            stats = screen_niche(seed, fetch, fee_cfg, thresholds, gates)
        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")
            errors.append({"seed": seed.name, "error": str(e)})
            continue
        results.append(stats)
        empty_streak = empty_streak + 1 if stats.cards_parsed == 0 else 0
        if empty_streak >= MAX_CONSECUTIVE_EMPTY:
            console.print("[red]Several empty result pages in a row: likely blocked. Stopping.[/red]")
            break

    ranked = rank(results)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json_mod.dumps({
        "seeds_file": str(seeds_path),
        "fees": asdict(fee_cfg),
        "thresholds": asdict(thresholds),
        "gates": asdict(gates),
        "pages": counters,
        "errors": errors,
        "niches": [asdict(s) for s in ranked],
    }, indent=2, default=str))

    table = Table(title="Niche screen (pre-owned, last ~90 days)")
    for col in ("#", "Niche", "Sold 90d", "Active", "STR", "Sold/wk", "p20", "p50",
                "Buy ceiling", "Deals", "Pool $/wk", "Gate"):
        table.add_column(col, justify="left" if col in ("Niche", "Gate") else "right")
    for n, s in enumerate(ranked, 1):
        table.add_row(
            str(n), s.name, str(s.sold_90d), "-" if s.active_now is None else str(s.active_now),
            "-" if s.str_pct is None else f"{s.str_pct:.0f}%", f"{s.sales_per_week:.1f}",
            _money(s.p20), _money(s.p50), _money(s.buy_ceiling), f"{s.deal_share_pct:.0f}%",
            f"{s.profit_pool_week:,.0f}",
            "[green]pass[/green]" if s.passes else f"[dim]{'; '.join(s.gate_failures)}[/dim]",
        )
    console.print(table)
    console.print(
        f"Pages fetched {counters['fetched']}, cached {counters['cached']}, "
        f"{counters['bytes'] / 1e6:.1f} MB HTML. Results: {out}"
    )


@app.command("scan-listings")
def scan_listings_cmd(
    from_path: Optional[Path] = typer.Option(None, "--from", help="niches.json from scan-niches"),
    top: int = typer.Option(10, "--top", help="Scan the top N passing niches"),
    seeds_path: Path = typer.Option(DEFAULT_SEEDS, "--seeds", help="Seed niches TOML file"),
    out: Optional[Path] = typer.Option(None, "--out", help="JSON output path"),
    cache_dir: Optional[Path] = typer.Option(None, "--cache-dir", help="HTML cache directory"),
):
    """Find live listings priced under each top niche's buy ceiling."""
    import json as json_mod
    from dataclasses import asdict

    from ebay_tracker.screener import NicheStats, default_cache_dir, load_seeds, scan_listings

    cache_dir = cache_dir or default_cache_dir()
    from_path = from_path or cache_dir / "niches.json"
    out = out or cache_dir / "candidates.json"
    data = json_mod.loads(from_path.read_text())
    niches = [NicheStats(**n) for n in data["niches"]]
    top_niches = [n for n in niches if n.passes][:top]
    seeds = {s.name: s for s in load_seeds(seeds_path)}
    fee_cfg, _ = _fee_and_thresholds()
    fetch, counters = _scan_fetcher(cache_dir / "html")

    candidates = []
    for stats in top_niches:
        seed = seeds.get(stats.name)
        if seed is None:
            console.print(f"[yellow]Seed '{stats.name}' not in {seeds_path}, skipping[/yellow]")
            continue
        console.print(f"[cyan]Scanning[/cyan] {stats.name} (ceiling {_money(stats.buy_ceiling)})")
        try:
            found = scan_listings(seed, stats, fetch, fee_cfg)
        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")
            continue
        console.print(f"  {len(found)} under ceiling")
        candidates.extend(found)

    candidates.sort(key=lambda c: c.profit_at_p50, reverse=True)
    out.write_text(json_mod.dumps({
        "from": str(from_path),
        "niches_scanned": [n.name for n in top_niches],
        "pages": counters,
        "candidates": [asdict(c) for c in candidates],
    }, indent=2, default=str))

    table = Table(title="Live listings under buy ceiling")
    for col in ("Niche", "Title", "Cost", "Ceiling", "Profit @p50", "Profit @p25", "Action", "Item"):
        table.add_column(col, justify="left" if col in ("Niche", "Title", "Action", "Item") else "right")
    for c in candidates:
        table.add_row(
            c.niche, c.title[:60], f"${c.total_cost:,.2f}", _money(c.buy_ceiling),
            f"${c.profit_at_p50:,.0f}", f"${c.profit_at_p25:,.0f}",
            c.action + (f" ({c.time_left})" if c.time_left else ""), c.item_id,
        )
    console.print(table)
    console.print(
        f"Pages fetched {counters['fetched']}, cached {counters['cached']}, "
        f"{counters['bytes'] / 1e6:.1f} MB HTML. Results: {out}"
    )
