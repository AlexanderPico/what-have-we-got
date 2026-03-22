# whgot — What Have We Got

CLI tool to identify items from photos or text lists and retrieve structured resale data. Built for eBay sellers, estate sale flippers, and resellers.

## Architecture

```
photo/text → [vision model via ollama] → structured JSON → [price enrichment] → [listing generation] → output
```

All processing is local-first. Vision models run via ollama. Price data from eBay completed listings + OpenLibrary, cached in SQLite.

## Project Structure

```
src/whgot/
  schema.py    — Pydantic data models (Item, Identifiers, PriceEstimate, Condition, etc.)
  parsing.py   — JSON response parser (handles markdown fences, malformed LLM output)
  vision.py    — Ollama vision integration: identify_image(), identify_text()
  pricing.py   — PriceCache (SQLite+TTL), OpenLibrary lookup, eBay completed listings scrape
  listing.py   — eBay listing generator: titles, descriptions, item specifics, pricing strategy
  condition.py — Condition grading: vision-based (ollama) + text heuristic fallback
  cli.py       — Typer CLI: identify, scan, ingest, price, listing, grade, version
tests/
  test_schema.py    — Schema validation + JSON parsing (6 tests)
  test_pricing.py   — Cache behavior, TTL, key priority (6 tests)
  test_listing.py   — Title gen, item specifics, pricing strategy (12 tests)
  test_condition.py — Text-based condition heuristics (5 tests)
```

## Commands

- `identify` — single item from photo
- `scan` — process directory of images (estate sale mode)
- `ingest` — text/CSV list processing
- `price` — enrich items with eBay comps + OpenLibrary
- `listing` — generate eBay listings
- `grade` — assess conditions from images
- `version` — print version

## Dev Workflow

```bash
pip install -e ".[dev]"
pytest tests/ -v          # 29 tests
ruff check src/ tests/    # lint
```

## Key Decisions

- **Vision model**: ollama with llava:13b default. Alternatives: moondream (fast), minicpm-v (multilingual), llava:34b (accurate)
- **Structured output**: Pydantic models with JSON serialization. parsing.py handles LLM output quirks.
- **Price cache**: SQLite in ~/.whgot/price_cache.db with configurable TTL (default 7 days)
- **No cloud dependency for core identification**. Cloud APIs are optional enrichment only.

## Conventions

- Python 3.10+, type hints everywhere
- Pydantic v2 for all data models
- Typer for CLI, Rich for terminal output
- Tests don't require ollama (parsing/schema/listing/condition tests are all offline)
- Vision tests require ollama running locally
