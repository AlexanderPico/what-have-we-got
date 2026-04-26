"""CLI entry point for whgot."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from whgot import __version__
from whgot.eval import evaluate_manifest_results, write_eval_report
from whgot.schema import Item
from whgot.triage import assess_items
from whgot.vision import DEFAULT_MODEL, identify_image, identify_text

app = typer.Typer(
    name="whgot",
    help="What Have We Got — identify items from photos or text for resale.",
    no_args_is_help=True,
)
console = Console()

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".bmp", ".tiff", ".tif"}


def _apply_triage(items: list[Item]) -> list[Item]:
    return assess_items(items)


def _item_rows(items: list[Item]) -> list[dict[str, object]]:
    items = _apply_triage(items)
    rows: list[dict[str, object]] = []
    for item in items:
        rows.append(
            {
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
                "price_comp_count": item.pricing.comp_count or "",
                "price_warning": item.pricing.warning or "",
                "triage_badge": item.triage.badge.value,
                "triage_score": item.triage.score,
                "source_image": item.source_image or "",
                "source_text": item.source_text or "",
            }
        )
    return rows


def _output_items(items: list[Item], output: Optional[Path], fmt: str) -> None:
    """Write items to stdout or file in the requested format."""
    items = _apply_triage(items)

    if fmt == "json":
        data = [item.model_dump(mode="json", exclude_none=True) for item in items]
        text = json.dumps(data, indent=2)
    elif fmt == "csv":
        rows = _item_rows(items)
        if not rows:
            console.print("[yellow]No items to output.[/yellow]")
            return
        if output:
            with open(output, "w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            console.print(f"[green]Wrote {len(rows)} items to {output}[/green]")
            return

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        text = buffer.getvalue()
    elif fmt == "table":
        table = Table(title=f"Identified Items ({len(items)})")
        table.add_column("#", style="dim", width=4)
        table.add_column("Name", style="bold", max_width=32)
        table.add_column("Category", width=14)
        table.add_column("Triage", width=16)
        table.add_column("Cond.", width=12)
        table.add_column("Conf.", width=6, justify="right")
        table.add_column("Price", width=14, justify="right")
        table.add_column("Source", width=18)

        for index, item in enumerate(items, 1):
            if item.pricing.median:
                price_text = f"~${item.pricing.median:.2f}"
            elif item.pricing.low and item.pricing.high:
                price_text = f"${item.pricing.low:.0f}-${item.pricing.high:.0f}"
            else:
                price_text = ""

            condition_text = (
                item.condition.value.replace("_", " ")
                if item.condition.value != "unknown"
                else ""
            )
            triage_text = f"{item.triage.badge.value} ({item.triage.score:.0f})"
            source_text = item.pricing.source or ""
            if item.pricing.warning:
                source_text = f"{source_text}*" if source_text else "heuristic*"

            table.add_row(
                str(index),
                item.name,
                item.category.value,
                triage_text,
                condition_text,
                f"{item.confidence:.0%}",
                price_text,
                source_text,
            )

        console.print(table)
        if any(item.pricing.warning for item in items):
            console.print("[dim]* heuristic pricing source[/dim]")
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
        text = json.dumps([listing.to_dict() for listing in listings], indent=2)
    elif fmt == "table":
        table = Table(title=f"eBay Listings ({len(listings)})")
        table.add_column("#", style="dim", width=4)
        table.add_column("Title", style="bold", max_width=44)
        table.add_column("Category", width=20)
        table.add_column("Condition", width=12)
        table.add_column("Strategy", width=10)
        table.add_column("Price", width=18, justify="right")

        for index, listing in enumerate(listings, 1):
            if listing.pricing_strategy == "auction":
                price_text = f"${listing.starting_bid:.2f} start"
                if listing.buy_it_now:
                    price_text += f" / ${listing.buy_it_now:.2f} BIN"
            else:
                price_text = (
                    f"${listing.suggested_price:.2f}"
                    if listing.suggested_price
                    else "N/A"
                )
            table.add_row(
                str(index),
                listing.title[:44],
                listing.category_name.split(" > ")[-1],
                listing.condition_name,
                listing.pricing_strategy,
                price_text,
            )
        console.print(table)
        return
    elif fmt == "csv":
        rows = [listing.to_dict() for listing in listings]
        if not rows:
            return
        if output:
            with open(output, "w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            console.print(f"[green]Wrote {len(rows)} listings to {output}[/green]")
            return

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        text = buffer.getvalue()
    else:
        raise typer.BadParameter(f"Unknown format: {fmt}")

    if output:
        output.write_text(text)
        console.print(f"[green]Wrote {len(listings)} listings to {output}[/green]")
    else:
        console.print(text)


def _maybe_enrich_prices(items: list[Item], do_price: bool) -> list[Item]:
    if not do_price:
        return _apply_triage(items)

    from whgot.pricing import enrich_prices

    console.print("[dim]Looking up prices...[/dim]")
    enriched = enrich_prices(items)
    priced = sum(1 for item in enriched if item.pricing.median or item.pricing.low)
    console.print(f"[green]Found pricing for {priced}/{len(enriched)} items[/green]")
    return _apply_triage(enriched)


def _load_items_from_json(path: Path) -> list[Item]:
    raw = json.loads(path.read_text())
    if isinstance(raw, dict):
        raw = [raw]
    return [Item(**entry) for entry in raw]


@app.command()
def identify(
    image: Path = typer.Argument(..., help="Path to image file."),
    batch: bool = typer.Option(
        False,
        "--batch",
        "-b",
        help="Batch or shelf mode: identify multiple items in one image.",
    ),
    price: bool = typer.Option(False, "--price", "-p", help="Also look up pricing data."),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Ollama vision model."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path."),
    fmt: str = typer.Option("table", "--format", "-f", help="table, json, or csv"),
) -> None:
    """Identify item(s) in a photo using a local vision model."""
    if not image.exists():
        console.print(f"[red]Error: Image not found: {image}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Identifying items in {image.name} using {model}...[/dim]")
    try:
        items = identify_image(image, model=model, batch_mode=batch)
    except ConnectionError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(1) from exc
    except ValueError as exc:
        console.print(f"[red]Parse error: {exc}[/red]")
        raise typer.Exit(1) from exc

    if not items:
        console.print("[yellow]No items identified.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[green]Identified {len(items)} item(s)[/green]")
    items = _maybe_enrich_prices(items, price)
    console.print()
    _output_items(items, output, fmt)


@app.command()
def scan(
    directory: Path = typer.Argument(..., help="Directory containing images to process."),
    batch: bool = typer.Option(
        True,
        "--batch/--single",
        "-b/-s",
        help="Batch mode (default) treats each image as containing multiple items.",
    ),
    price: bool = typer.Option(False, "--price", "-p", help="Also look up pricing data."),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Ollama vision model."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path."),
    fmt: str = typer.Option("table", "--format", "-f", help="table, json, or csv"),
) -> None:
    """Scan a directory of images and identify items across all photos."""
    if not directory.is_dir():
        console.print(f"[red]Error: Not a directory: {directory}[/red]")
        raise typer.Exit(1)

    images = sorted(
        file
        for file in directory.iterdir()
        if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not images:
        console.print(f"[yellow]No image files found in {directory}[/yellow]")
        raise typer.Exit(0)

    console.print(f"[dim]Found {len(images)} images in {directory}[/dim]\n")
    all_items: list[Item] = []
    for index, image_file in enumerate(images, 1):
        console.print(f"[dim][{index}/{len(images)}] Processing {image_file.name}...[/dim]")
        try:
            items = identify_image(image_file, model=model, batch_mode=batch)
            console.print(f"  [green]→ {len(items)} item(s)[/green]")
            all_items.extend(items)
        except ConnectionError as exc:
            console.print(f"[red]Error: {exc}[/red]")
            raise typer.Exit(1) from exc
        except Exception as exc:
            console.print(
                f"  [yellow]Warning: Failed to process {image_file.name}: {exc}[/yellow]"
            )

    if not all_items:
        console.print("[yellow]No items identified across all images.[/yellow]")
        raise typer.Exit(0)

    console.print(f"\n[green]Total: {len(all_items)} items from {len(images)} images[/green]")
    all_items = _maybe_enrich_prices(all_items, price)
    console.print()
    _output_items(all_items, output, fmt)


@app.command()
def ingest(
    source: Path = typer.Argument(..., help="Text or CSV file with item descriptions."),
    price: bool = typer.Option(False, "--price", "-p", help="Also look up pricing data."),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Ollama model to use."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path."),
    fmt: str = typer.Option("table", "--format", "-f", help="table, json, or csv"),
) -> None:
    """Process a text or CSV list of item descriptions into structured items."""
    if not source.exists():
        console.print(f"[red]Error: File not found: {source}[/red]")
        raise typer.Exit(1)

    descriptions: list[str] = []
    if source.suffix.lower() == ".csv":
        with open(source, newline="") as handle:
            reader = csv.reader(handle)
            for row in reader:
                description = next((cell.strip() for cell in row if cell.strip()), None)
                if description:
                    descriptions.append(description)
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
    for index, description in enumerate(descriptions, 1):
        console.print(f"[dim]  [{index}/{len(descriptions)}] {description[:60]}...[/dim]")
        try:
            items.append(identify_text(description, model=model))
        except Exception as exc:
            console.print(
                f"[yellow]  Warning: Failed to identify '{description[:40]}': {exc}[/yellow]"
            )

    console.print(f"[green]Identified {len(items)} item(s)[/green]")
    items = _maybe_enrich_prices(items, price)
    console.print()
    _output_items(items, output, fmt)


@app.command()
def price(
    input_file: Path = typer.Argument(..., help="JSON file with items."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path."),
    fmt: str = typer.Option("table", "--format", "-f", help="table, json, or csv"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip the local price cache."),
) -> None:
    """Enrich previously identified items with pricing data."""
    if not input_file.exists():
        console.print(f"[red]Error: File not found: {input_file}[/red]")
        raise typer.Exit(1)

    try:
        items = _load_items_from_json(input_file)
    except Exception as exc:
        console.print(f"[red]Error parsing {input_file}: {exc}[/red]")
        raise typer.Exit(1) from exc

    console.print(f"[dim]Enriching {len(items)} items with pricing data...[/dim]")
    from whgot.pricing import enrich_prices

    enriched = enrich_prices(items, use_cache=not no_cache)
    enriched = _apply_triage(enriched)
    priced = sum(1 for item in enriched if item.pricing.median or item.pricing.low)
    console.print(f"[green]Found pricing for {priced}/{len(enriched)} items[/green]\n")
    _output_items(enriched, output, fmt)


@app.command()
def listing(
    input_file: Path = typer.Argument(..., help="JSON file with items."),
    use_llm: bool = typer.Option(
        True,
        "--llm/--no-llm",
        help="Use LLM for title optimization (default: yes).",
    ),
    model: str = typer.Option(
        DEFAULT_MODEL,
        "--model",
        "-m",
        help="Ollama model for title generation.",
    ),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path."),
    fmt: str = typer.Option("table", "--format", "-f", help="table, json, or csv"),
) -> None:
    """Generate eBay listing drafts from identified items."""
    if not input_file.exists():
        console.print(f"[red]Error: File not found: {input_file}[/red]")
        raise typer.Exit(1)

    try:
        items = _load_items_from_json(input_file)
    except Exception as exc:
        console.print(f"[red]Error parsing {input_file}: {exc}[/red]")
        raise typer.Exit(1) from exc

    console.print(f"[dim]Generating {len(items)} eBay listings...[/dim]")
    from whgot.listing import generate_listings

    listings = generate_listings(items, use_llm=use_llm, model=model)
    console.print(f"[green]Generated {len(listings)} listings[/green]\n")
    _output_listings(listings, output, fmt)


@app.command()
def grade(
    input_file: Path = typer.Argument(
        ...,
        help="JSON file with items that have source_image paths.",
    ),
    model: str = typer.Option(
        DEFAULT_MODEL,
        "--model",
        "-m",
        help="Ollama vision model for grading.",
    ),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path."),
    fmt: str = typer.Option("table", "--format", "-f", help="table, json, or csv"),
) -> None:
    """Assess item conditions from their source images."""
    if not input_file.exists():
        console.print(f"[red]Error: File not found: {input_file}[/red]")
        raise typer.Exit(1)

    try:
        items = _load_items_from_json(input_file)
    except Exception as exc:
        console.print(f"[red]Error parsing {input_file}: {exc}[/red]")
        raise typer.Exit(1) from exc

    with_images = [item for item in items if item.source_image]
    console.print(
        f"[dim]Grading conditions for {len(with_images)}/{len(items)} items with images...[/dim]"
    )
    from whgot.condition import grade_conditions

    graded = grade_conditions(with_images, model=model)
    all_items = graded + [item for item in items if not item.source_image]
    all_items = _apply_triage(all_items)

    graded_count = sum(1 for item in all_items if item.condition.value != "unknown")
    console.print(f"[green]Graded {graded_count}/{len(all_items)} items[/green]\n")
    _output_items(all_items, output, fmt)


@app.command("eval-report")
def eval_report(
    manifest_file: Path = typer.Argument(..., help="Benchmark manifest JSON file."),
    predictions_file: Path = typer.Argument(..., help="Predicted items JSON file."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Report output path."),
) -> None:
    """Compare predicted items against a benchmark manifest and emit a report."""
    if not manifest_file.exists():
        console.print(f"[red]Error: Manifest not found: {manifest_file}[/red]")
        raise typer.Exit(1)
    if not predictions_file.exists():
        console.print(f"[red]Error: Predictions not found: {predictions_file}[/red]")
        raise typer.Exit(1)

    try:
        results, summary = evaluate_manifest_results(manifest_file, predictions_file)
    except Exception as exc:
        console.print(f"[red]Error running eval: {exc}[/red]")
        raise typer.Exit(1) from exc

    report_path = output or predictions_file.with_name(f"{predictions_file.stem}.eval-report.json")
    write_eval_report(results, summary, report_path)

    table = Table(title="Eval Summary")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Total", str(summary.total))
    table.add_row("Category accuracy", f"{summary.category_accuracy:.2%}")
    table.add_row("Name accuracy", f"{summary.name_accuracy:.2%}")
    table.add_row("Metadata hit rate", f"{summary.metadata_hit_rate:.2%}")
    console.print(table)
    console.print(f"[green]Wrote eval report to {report_path}[/green]")


@app.command()
def version() -> None:
    """Print version and exit."""
    console.print(f"whgot {__version__}")


if __name__ == "__main__":
    app()
