"""CLI entry point for whgot.

Usage:
    whgot identify photo.jpg                    # single item
    whgot identify --batch shelf.jpg            # multiple items from shelf photo
    whgot identify --batch --price shelf.jpg    # identify + price lookup
    whgot scan ./photos/                        # process all images in a directory
    whgot ingest items.txt                      # text list → structured items
    whgot price inventory.json                  # enrich existing items with pricing
    whgot listing inventory.json                # generate eBay listings
    whgot grade inventory.json                  # assess item conditions from images
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from whgot import __version__
from whgot.schema import Item
from whgot.vision import DEFAULT_MODEL, identify_image, identify_text

app = typer.Typer(
    name="whgot",
    help="What Have We Got — identify items from photos or text for resale.",
    no_args_is_help=True,
)
console = Console()

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".bmp", ".tiff", ".tif"}


# --- Output Formatters ---


def _output_items(items: list[Item], output: Optional[Path], fmt: str) -> None:
    """Write items to stdout or file in the requested format."""
    if fmt == "json":
        data = [item.model_dump(mode="json", exclude_none=True) for item in items]
        text = json.dumps(data, indent=2)
    elif fmt == "csv":
        rows = []
        for item in items:
            row = {
                "name": item.name,
                "category": item.category.value,
                "condition": item.condition.value,
                "confidence": item.confidence,
                "description": item.description or "",
                "author": item.metadata.author or "",
                "brand": item.metadata.brand or "",
                "franchise": item.metadata.franchise or "",
                "isbn": item.identifiers.isbn or item.identifiers.isbn13 or "",
                "upc": item.identifiers.upc or "",
                "price_low": item.pricing.low or "",
                "price_high": item.pricing.high or "",
                "price_median": item.pricing.median or "",
                "price_source": item.pricing.source or "",
                "source_image": item.source_image or "",
            }
            rows.append(row)

        if not rows:
            console.print("[yellow]No items to output.[/yellow]")
            return

        if output:
            with open(output, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            console.print(f"[green]Wrote {len(rows)} items to {output}[/green]")
            return
        else:
            import io

            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
            text = buf.getvalue()
    elif fmt == "table":
        table = Table(title=f"Identified Items ({len(items)})")
        table.add_column("#", style="dim", width=4)
        table.add_column("Name", style="bold", max_width=40)
        table.add_column("Category", width=12)
        table.add_column("Cond.", width=10)
        table.add_column("Conf.", width=6, justify="right")
        table.add_column("Details", max_width=30)
        table.add_column("Price Est.", width=14, justify="right")

        for i, item in enumerate(items, 1):
            details = []
            if item.metadata.author:
                details.append(f"by {item.metadata.author}")
            if item.metadata.brand:
                details.append(item.metadata.brand)
            if item.metadata.franchise:
                details.append(item.metadata.franchise)
            if item.metadata.character:
                details.append(item.metadata.character)

            # Format price range
            price_str = ""
            if item.pricing.median:
                price_str = f"~${item.pricing.median:.2f}"
            elif item.pricing.low and item.pricing.high:
                price_str = f"${item.pricing.low:.0f}-${item.pricing.high:.0f}"

            # Condition display
            cond_str = item.condition.value.replace("_", " ") if item.condition.value != "unknown" else ""

            table.add_row(
                str(i),
                item.name,
                item.category.value,
                cond_str,
                f"{item.confidence:.0%}",
                ", ".join(details) if details else (item.description or "")[:30],
                price_str,
            )

        console.print(table)
        return
    else:
        raise typer.BadParameter(f"Unknown format: {fmt}")

    if output:
        output.write_text(text)
        console.print(f"[green]Wrote {len(items)} items to {output}[/green]")
    else:
        console.print(text)


def _output_listings(listings: list, output: Optional[Path], fmt: str) -> None:
    """Write eBay listings to stdout or file."""
    if fmt == "json":
        data = [lst.to_dict() for lst in listings]
        text = json.dumps(data, indent=2)
    elif fmt == "table":
        table = Table(title=f"eBay Listings ({len(listings)})")
        table.add_column("#", style="dim", width=4)
        table.add_column("Title", style="bold", max_width=50)
        table.add_column("Category", width=20)
        table.add_column("Condition", width=12)
        table.add_column("Strategy", width=10)
        table.add_column("Price", width=12, justify="right")

        for i, lst in enumerate(listings, 1):
            if lst.pricing_strategy == "auction":
                price_str = f"${lst.starting_bid:.2f} start"
                if lst.buy_it_now:
                    price_str += f" / ${lst.buy_it_now:.2f} BIN"
            else:
                price_str = f"${lst.suggested_price:.2f}" if lst.suggested_price else "N/A"

            table.add_row(
                str(i),
                lst.title[:50],
                lst.category_name.split(" > ")[-1],
                lst.condition_name,
                lst.pricing_strategy,
                price_str,
            )

        console.print(table)
        return
    elif fmt == "csv":
        import io

        rows = []
        for lst in listings:
            rows.append({
                "title": lst.title,
                "category_id": lst.category_id,
                "category_name": lst.category_name,
                "condition_id": lst.condition_id,
                "condition_name": lst.condition_name,
                "pricing_strategy": lst.pricing_strategy,
                "suggested_price": lst.suggested_price or "",
                "starting_bid": lst.starting_bid or "",
                "buy_it_now": lst.buy_it_now or "",
            })
        if not rows:
            return
        if output:
            with open(output, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            console.print(f"[green]Wrote {len(rows)} listings to {output}[/green]")
            return
        else:
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
            text = buf.getvalue()
    else:
        raise typer.BadParameter(f"Unknown format: {fmt}")

    if output:
        output.write_text(text)
        console.print(f"[green]Wrote {len(listings)} listings to {output}[/green]")
    else:
        console.print(text)


def _maybe_enrich_prices(items: list[Item], do_price: bool) -> list[Item]:
    """Optionally run price enrichment on a list of items."""
    if not do_price:
        return items

    from whgot.pricing import enrich_prices

    console.print("[dim]Looking up prices...[/dim]")
    enriched = enrich_prices(items)
    priced = sum(1 for i in enriched if i.pricing.median or i.pricing.low)
    console.print(f"[green]Found pricing for {priced}/{len(enriched)} items[/green]")
    return enriched


def _load_items_from_json(path: Path) -> list[Item]:
    """Load items from a JSON file (output of identify/ingest/scan)."""
    raw = json.loads(path.read_text())
    if isinstance(raw, dict):
        raw = [raw]
    return [Item(**entry) for entry in raw]


# --- Commands ---


@app.command()
def identify(
    image: Path = typer.Argument(..., help="Path to image file (jpg, png, webp, etc.)"),
    batch: bool = typer.Option(
        False, "--batch", "-b", help="Batch/shelf mode: identify multiple items in one image"
    ),
    price: bool = typer.Option(
        False, "--price", "-p", help="Also look up pricing data for identified items"
    ),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Ollama vision model to use"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path"),
    fmt: str = typer.Option(
        "table", "--format", "-f", help="Output format: table, json, csv"
    ),
) -> None:
    """Identify item(s) in a photo using a local vision model."""
    if not image.exists():
        console.print(f"[red]Error: Image not found: {image}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Identifying items in {image.name} using {model}...[/dim]")

    try:
        items = identify_image(image, model=model, batch_mode=batch)
    except ConnectionError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Parse error: {e}[/red]")
        raise typer.Exit(1)

    if not items:
        console.print("[yellow]No items identified.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[green]Identified {len(items)} item(s)[/green]")
    items = _maybe_enrich_prices(items, price)
    console.print()
    _output_items(items, output, fmt)


@app.command()
def scan(
    directory: Path = typer.Argument(..., help="Directory containing images to process"),
    batch: bool = typer.Option(
        True, "--batch/--single", "-b/-s",
        help="Batch mode (default): treat each image as containing multiple items"
    ),
    price: bool = typer.Option(
        False, "--price", "-p", help="Also look up pricing data"
    ),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Ollama vision model to use"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path"),
    fmt: str = typer.Option(
        "table", "--format", "-f", help="Output format: table, json, csv"
    ),
) -> None:
    """Scan a directory of images, identifying all items across all photos.

    This is the "estate sale mode" — point it at a folder of photos and get
    a complete inventory. Each image is processed in batch mode by default.
    """
    if not directory.is_dir():
        console.print(f"[red]Error: Not a directory: {directory}[/red]")
        raise typer.Exit(1)

    # Collect all image files
    images = sorted(
        f for f in directory.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
    )

    if not images:
        console.print(f"[yellow]No image files found in {directory}[/yellow]")
        raise typer.Exit(0)

    console.print(f"[dim]Found {len(images)} images in {directory}[/dim]\n")

    all_items: list[Item] = []
    for i, img in enumerate(images, 1):
        console.print(f"[dim][{i}/{len(images)}] Processing {img.name}...[/dim]")
        try:
            items = identify_image(img, model=model, batch_mode=batch)
            console.print(f"  [green]→ {len(items)} item(s)[/green]")
            all_items.extend(items)
        except ConnectionError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"  [yellow]Warning: Failed to process {img.name}: {e}[/yellow]")

    if not all_items:
        console.print("[yellow]No items identified across all images.[/yellow]")
        raise typer.Exit(0)

    console.print(f"\n[green]Total: {len(all_items)} items from {len(images)} images[/green]")
    all_items = _maybe_enrich_prices(all_items, price)
    console.print()
    _output_items(all_items, output, fmt)


@app.command()
def ingest(
    source: Path = typer.Argument(..., help="Text file (.txt) or CSV file (.csv) with item list"),
    price: bool = typer.Option(
        False, "--price", "-p", help="Also look up pricing data for identified items"
    ),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Ollama model to use"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path"),
    fmt: str = typer.Option(
        "table", "--format", "-f", help="Output format: table, json, csv"
    ),
) -> None:
    """Process a text or CSV list of item descriptions into structured data."""
    if not source.exists():
        console.print(f"[red]Error: File not found: {source}[/red]")
        raise typer.Exit(1)

    descriptions: list[str] = []

    if source.suffix.lower() == ".csv":
        with open(source, newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                desc = next((cell.strip() for cell in row if cell.strip()), None)
                if desc:
                    descriptions.append(desc)
    else:
        descriptions = [
            line.strip()
            for line in source.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    if not descriptions:
        console.print("[yellow]No item descriptions found in file.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[dim]Processing {len(descriptions)} items using {model}...[/dim]")

    items: list[Item] = []
    for i, desc in enumerate(descriptions, 1):
        console.print(f"[dim]  [{i}/{len(descriptions)}] {desc[:60]}...[/dim]")
        try:
            item = identify_text(desc, model=model)
            items.append(item)
        except Exception as e:
            console.print(f"[yellow]  Warning: Failed to identify '{desc[:40]}': {e}[/yellow]")

    console.print(f"[green]Identified {len(items)} item(s)[/green]")
    items = _maybe_enrich_prices(items, price)
    console.print()
    _output_items(items, output, fmt)


@app.command()
def price(
    input_file: Path = typer.Argument(..., help="JSON file with items (output of identify/ingest)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path"),
    fmt: str = typer.Option(
        "table", "--format", "-f", help="Output format: table, json, csv"
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache", help="Skip the local price cache, always fetch fresh"
    ),
) -> None:
    """Enrich previously identified items with pricing data.

    Reads a JSON file (output of `whgot identify -f json`) and adds
    price estimates from eBay completed listings and OpenLibrary.
    """
    if not input_file.exists():
        console.print(f"[red]Error: File not found: {input_file}[/red]")
        raise typer.Exit(1)

    try:
        items = _load_items_from_json(input_file)
    except Exception as e:
        console.print(f"[red]Error parsing {input_file}: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Enriching {len(items)} items with pricing data...[/dim]")

    from whgot.pricing import enrich_prices

    enriched = enrich_prices(items, use_cache=not no_cache)
    priced = sum(1 for i in enriched if i.pricing.median or i.pricing.low)
    console.print(f"[green]Found pricing for {priced}/{len(enriched)} items[/green]\n")

    _output_items(enriched, output, fmt)


@app.command()
def listing(
    input_file: Path = typer.Argument(..., help="JSON file with items (output of identify/price)"),
    use_llm: bool = typer.Option(
        True, "--llm/--no-llm", help="Use LLM for title optimization (default: yes)"
    ),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Ollama model for title generation"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path"),
    fmt: str = typer.Option(
        "table", "--format", "-f", help="Output format: table, json, csv"
    ),
) -> None:
    """Generate eBay listings from identified items.

    Produces keyword-optimized titles (80 chars max), item specifics,
    markdown descriptions, and pricing strategy suggestions.
    """
    if not input_file.exists():
        console.print(f"[red]Error: File not found: {input_file}[/red]")
        raise typer.Exit(1)

    try:
        items = _load_items_from_json(input_file)
    except Exception as e:
        console.print(f"[red]Error parsing {input_file}: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Generating {len(items)} eBay listings...[/dim]")

    from whgot.listing import generate_listings

    listings = generate_listings(items, use_llm=use_llm, model=model)
    console.print(f"[green]Generated {len(listings)} listings[/green]\n")

    _output_listings(listings, output, fmt)


@app.command()
def grade(
    input_file: Path = typer.Argument(..., help="JSON file with items that have source_image paths"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Ollama vision model for grading"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path"),
    fmt: str = typer.Option(
        "table", "--format", "-f", help="Output format: table, json, csv"
    ),
) -> None:
    """Assess item conditions from their source images.

    Reads a JSON file with items (must have source_image paths) and
    grades each item's condition using vision analysis.
    """
    if not input_file.exists():
        console.print(f"[red]Error: File not found: {input_file}[/red]")
        raise typer.Exit(1)

    try:
        items = _load_items_from_json(input_file)
    except Exception as e:
        console.print(f"[red]Error parsing {input_file}: {e}[/red]")
        raise typer.Exit(1)

    with_images = [i for i in items if i.source_image]
    console.print(
        f"[dim]Grading conditions for {len(with_images)}/{len(items)} items with images...[/dim]"
    )

    from whgot.condition import grade_conditions

    graded = grade_conditions(with_images, model=model)

    # Merge graded items back with any that didn't have images
    no_images = [i for i in items if not i.source_image]
    all_items = graded + no_images

    graded_count = sum(1 for i in all_items if i.condition.value != "unknown")
    console.print(f"[green]Graded {graded_count}/{len(all_items)} items[/green]\n")

    _output_items(all_items, output, fmt)


@app.command()
def version() -> None:
    """Print version and exit."""
    console.print(f"whgot {__version__}")


if __name__ == "__main__":
    app()
