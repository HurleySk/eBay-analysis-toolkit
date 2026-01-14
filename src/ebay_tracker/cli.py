from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ebay_tracker.config import get_config
from ebay_tracker.db import Database
from ebay_tracker.models import Search

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


if __name__ == "__main__":
    app()
