"""Tests for the pricing engine — cache behavior, key generation, enrichment."""

import tempfile
from pathlib import Path

from whgot.pricing import PriceCache, enrich_price
from whgot.schema import Identifiers, Item, ItemCategory, PriceEstimate


def test_cache_roundtrip():
    """Price cache should store and retrieve estimates by item key."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = PriceCache(cache_dir=Path(tmpdir), ttl_days=1)
        item = Item(
            name="The Manga Guide to Relativity",
            category=ItemCategory.BOOK,
            identifiers=Identifiers(isbn13="9781593272722"),
        )
        estimate = PriceEstimate(
            low=5.0,
            high=15.0,
            median=8.50,
            source="test",
            comp_count=3,
            warning="heuristic",
        )
        cache.put(item, estimate)

        cached = cache.get(item)
        assert cached is not None
        assert cached.median == 8.50
        assert cached.source == "test"
        assert cached.comp_count == 3
        assert cached.warning == "heuristic"


def test_cache_key_isbn_priority():
    """Cache key should prefer ISBN over name when available."""
    item_isbn = Item(
        name="Some Book",
        identifiers=Identifiers(isbn13="9781593272722"),
    )
    assert PriceCache._make_key(item_isbn) == "isbn13:9781593272722"

    item_name = Item(name="Mystery Object", category=ItemCategory.TOY)
    key = PriceCache._make_key(item_name)
    assert key.startswith("name:toy:")
    assert "mystery object" in key


def test_cache_key_upc():
    """Cache key should use UPC when no ISBN is available."""
    item = Item(
        name="Some DVD",
        category=ItemCategory.DVD,
        identifiers=Identifiers(upc="085391631729"),
    )
    assert PriceCache._make_key(item) == "upc:085391631729"


def test_cache_miss_on_empty():
    """Cache should return None for items never stored."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = PriceCache(cache_dir=Path(tmpdir), ttl_days=1)
        assert cache.get(Item(name="Never Seen Before")) is None


def test_cache_ttl_expiration():
    """Expired cache entries should return None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = PriceCache(cache_dir=Path(tmpdir), ttl_days=0)
        item = Item(name="Stale Item")
        cache.put(item, PriceEstimate(low=1.0, high=5.0, median=3.0, source="test"))
        assert cache.get(item) is None


def test_enrich_price_uses_cache():
    """enrich_price should return cached result without hitting network."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = PriceCache(cache_dir=Path(tmpdir), ttl_days=1)
        item = Item(
            name="Blade Runner: The Director's Cut",
            category=ItemCategory.DVD,
            identifiers=Identifiers(upc="085391631729"),
        )
        estimate = PriceEstimate(low=4.0, high=12.0, median=7.50, source="ebay_completed")
        cache.put(item, estimate)

        enriched = enrich_price(item, use_cache=True, cache_dir=Path(tmpdir))
        assert enriched.pricing.median == 7.50
        assert enriched.pricing.source == "ebay_completed"
