# whgot — What Have We Got

CLI tool that identifies items from photos or text lists and returns structured resale data. Built for eBay sellers, estate sale flippers, and anyone who wants to know what they've got.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) running locally with a vision model

## Quick Start

```bash
# Install ollama and pull a vision model
ollama pull llava:13b

# Install whgot
pip install -e .

# Identify a single item from a photo
whgot identify photo.jpg

# Scan a shelf of books/DVDs (batch mode)
whgot identify --batch shelf.jpg

# Process a text list
whgot identify items.txt

# Output as JSON or CSV
whgot identify --batch shelf.jpg -f json -o inventory.json
whgot identify --batch shelf.jpg -f csv -o inventory.csv
```

## Architecture

```
photo/text → [vision model via ollama] → structured JSON → [price enrichment] → output
```

All processing is local. No cloud APIs required for core identification.
