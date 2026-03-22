"""Tests for the Item schema — ensures serialization roundtrips and validation."""

import json

from whgot.schema import Condition, Identifiers, Item, ItemCategory, ItemMetadata


def test_item_minimal():
    """Minimal Item with just a name should serialize cleanly."""
    item = Item(name="Mystery Object")
    assert item.name == "Mystery Object"
    assert item.category == ItemCategory.OTHER
    assert item.condition == Condition.UNKNOWN
    assert item.confidence == 0.0


def test_item_full_roundtrip():
    """A fully-populated Item should survive JSON serialization roundtrip."""
    item = Item(
        name="The Manga Guide to Relativity",
        category=ItemCategory.BOOK,
        condition=Condition.VERY_GOOD,
        confidence=0.92,
        description="Softcover, no starch press, clean spine, no markings",
        metadata=ItemMetadata(
            author="Hideo Nitta",
            publisher="No Starch Press",
            year_published=2011,
            format="softcover",
            genre="science / manga",
        ),
        identifiers=Identifiers(isbn="1593272723", isbn13="9781593272722"),
        source_image="book_1.jpg",
    )

    # Roundtrip through JSON
    data = json.loads(item.model_dump_json(exclude_none=True))
    rebuilt = Item(**data)

    assert rebuilt.name == item.name
    assert rebuilt.metadata.author == "Hideo Nitta"
    assert rebuilt.identifiers.isbn13 == "9781593272722"
    assert rebuilt.confidence == 0.92


def test_item_summary():
    """Summary method should produce a readable one-liner."""
    item = Item(
        name="Air Max 90",
        metadata=ItemMetadata(brand="Nike"),
        condition=Condition.GOOD,
    )
    summary = item.summary()
    assert "Air Max 90" in summary
    assert "Nike" in summary
    assert "good" in summary


def test_category_enum_from_string():
    """Category should be constructable from plain strings (model output)."""
    assert ItemCategory("book") == ItemCategory.BOOK
    assert ItemCategory("dvd") == ItemCategory.DVD
    assert ItemCategory("toy") == ItemCategory.TOY


def test_parse_response_json():
    """Test the response parser handles well-formed model output."""
    from whgot.parsing import parse_items_response

    raw = json.dumps([
        {
            "name": "Blade Runner: The Director's Cut",
            "category": "dvd",
            "confidence": 0.85,
            "description": "DVD case, standard width",
            "metadata": {"director": "Ridley Scott", "genre": "sci-fi"},
            "identifiers": {"upc": "085391631729"},
        }
    ])

    items = parse_items_response(raw)
    assert len(items) == 1
    assert items[0].name == "Blade Runner: The Director's Cut"
    assert items[0].category == ItemCategory.DVD
    assert items[0].metadata.director == "Ridley Scott"


def test_parse_response_with_markdown_fences():
    """Parser should handle models that wrap JSON in markdown code fences."""
    from whgot.parsing import parse_items_response

    raw = """```json
[{"name": "Test Item", "category": "other", "confidence": 0.5}]
```"""

    items = parse_items_response(raw)
    assert len(items) == 1
    assert items[0].name == "Test Item"
