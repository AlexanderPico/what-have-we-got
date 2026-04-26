# whgot — What Have We Got

Local-first seller research tool for identifying items from photos or text, pulling rough resale pricing, and generating listing drafts.

Primary workflows:
- identify likely items from photos or text descriptions
- estimate resale value from free/public sources
- triage items as worth checking / maybe / skip
- generate listing drafts and export item spreadsheets
- review saved analysis sessions in a local web UI

## Current product shape

`whgot` is now a local-first Python app with:
- CLI commands for identification, pricing, listing drafts, and grading
- a local FastAPI web UI for upload -> identify -> price -> listing-draft review
- saved sessions stored under `~/.whgot/sessions/`
- evaluation scaffolding under `eval/`

## Requirements

- Python 3.12 recommended
- [Ollama](https://ollama.com) running locally for identify/grade/listing-title flows
- a local vision model such as `llava:13b`

## Setup

```bash
python3.12 -m venv .venv312
. .venv312/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

## Quick start

### Pull a model

```bash
ollama pull llava:13b
```

### CLI examples

```bash
# Identify a single item from a photo
whgot identify photo.jpg

# Identify multiple items from a shelf photo and add price estimates
whgot identify --batch --price shelf.jpg

# Process a directory of images
whgot scan ./photos/ --price -f csv -o inventory.csv

# Process a text list
whgot ingest items.txt --price -f json -o items.json

# Price-enrich a prior JSON run
whgot price items.json -f json

# Generate listing drafts
whgot listing items.json -f json -o listings.json
```

### Web UI

```bash
whgot-web
```

Then open:
- http://127.0.0.1:8000

The web app saves session bundles under:
- `~/.whgot/sessions/`

Each session stores:
- `session.json`
- `items.csv`
- uploaded files used for that run

## Development checks

```bash
python -m pytest -q
ruff check src tests
python -m compileall src
```

## Evaluation scaffold

See:
- `eval/README.md`
- `eval/benchmark_schema.md`
- `eval/benchmarks/starter_manifest.json`

Recommended local-real image storage during development:
- `local-real-images/` (gitignored)

## Notes on pricing quality

Pricing is intentionally broad-coverage and free/public-source-first for v1.
Current pricing can come from:
- OpenLibrary metadata heuristics for books
- heuristic eBay completed-listing HTML scrape

That means pricing should be treated as seller triage assistance, not ground truth.
The app surfaces source names, heuristic warnings, and triage badges to help with this.

## Repo structure

```text
src/whgot/
  schema.py         canonical Item / pricing / triage models
  parsing.py        model response parser
  vision.py         Ollama image/text identification
  pricing.py        cache + source lookups
  triage.py         heuristic seller prioritization
  listing.py        listing draft generation
  condition.py      condition grading helpers
  eval.py           benchmark scoring helpers
  session_store.py  saved-session persistence under ~/.whgot/
  web_app.py        FastAPI web app
  web_templates/    Jinja templates
  web_static/       CSS assets
tests/
  fixtures/         parser and offline item fixtures
eval/
  benchmarks/       starter benchmark manifests
```

## Commands

- `identify` — identify item(s) in one image
- `scan` — process all images in a directory
- `ingest` — process text/CSV item descriptions
- `price` — enrich prior JSON output with pricing
- `listing` — generate listing drafts
- `grade` — estimate condition from source images
- `version` — print version
- `whgot-web` — run the local web app

## Limitations

- no direct marketplace posting
- pricing is heuristic and source-fragile in places
- multi-item shelf detection is prompt-based for now, not segmentation-based
- web UI is desktop-first in this phase
