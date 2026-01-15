from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ebay_tracker.analyzer import analyze_listings, get_recommendation
from ebay_tracker.config import get_config
from ebay_tracker.db import Database
from ebay_tracker.models import Search, FetchLog
from ebay_tracker.scraper import build_search_url, fetch_page, parse_listings, rate_limit_delay

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


@app.command()
def add(
    name: str = typer.Argument(..., help="Name for this search"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="eBay search query (defaults to name)"),
    condition: Optional[str] = typer.Option(None, "--condition", "-c", help="Item condition filter"),
    min_price: Optional[float] = typer.Option(None, "--min-price", help="Minimum price filter"),
    max_price: Optional[float] = typer.Option(None, "--max-price", help="Maximum price filter"),
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
    console.print(f"[cyan]Proxy:[/cyan]", end=" ")
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
    days: int = typer.Option(90, "--days", "-d", help="How many days back to fetch"),
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
            html = fetch_page(url, config.proxy_url)
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


if __name__ == "__main__":
    app()
