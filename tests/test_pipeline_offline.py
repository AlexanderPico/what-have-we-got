"""Offline pipeline tests using fixture items."""

import json
from pathlib import Path

from whgot.listing import generate_listings
from whgot.schema import Item
from whgot.triage import assess_items

FIXTURES = Path(__file__).parent / "fixtures" / "items"


def _load_items(name: str) -> list[Item]:
    raw = json.loads((FIXTURES / name).read_text())
    return [Item(**entry) for entry in raw]


def test_books_media_fixture_generates_listing():
    items = assess_items(_load_items("books_media_sample.json"))
    listings = generate_listings(items, use_llm=False)
    assert listings[0].category_id == "261186"
    assert items[0].triage.badge.value in {"worth_checking", "maybe"}


def test_toys_fixture_carries_packaging_into_listing():
    items = assess_items(_load_items("toys_collectibles_sample.json"))
    listing = generate_listings(items, use_llm=False)[0]
    assert listing.item_specifics["Packaging"] == "Original (Unopened)"


def test_electronics_fixture_has_model_specific():
    items = assess_items(_load_items("electronics_sample.json"))
    listing = generate_listings(items, use_llm=False)[0]
    assert listing.item_specifics["Model"] == "WM-FX195"
