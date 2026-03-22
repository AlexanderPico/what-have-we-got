"""Tests for the pricing engine — cache behavior, key generation, enrichment."""

import json
import tempfile
from pathlib import Path

from whgot.pricing import PriceCache, enrich_price
from whgot.schema import Identifiers, Item, ItemCategory, ItemMetadata, PriceEstimate


def test_cache_roundtrip():
    """Price cache should store and retrieve estimates by item key."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = PriceCache(cache_dir=Path(tmpdir), ttl_days=1)

        item = Item(
            name="The Manga Guide to Relativity",
            category=ItemCategory.BOOK,
            identifiers=Identifiers(isbn13="9781593272722"),
        )

        estimate = PriceEstimate(low=5.0, high=15.0, median=8.50, source="test")
        cache.put(item, estimate)

        # Should retrieve the cached value
        cached = cache.get(item)
        assert cached is not None
        assert cached.median == 8.50
        assert cached.source == "test"


def test_cache_key_isbn_priority():
    """Cache key should prefer ISBN over name when available."""
    cache = PriceCache.__new__(PriceCache)  # skip __init__ for unit test

    # Item with ISBN
    item_isbn = Item(
        name="Some Book",
        identifiers=Identifiers(isbn13="9781593272722"),
    )
    assert "isbn13:9781593272722" == PriceCache._make_key(item_isbn)

    # Item without ISBN falls back to name
    item_name = Item(name="Mystery Object", category=ItemCategory.TOY)
    key = PriceCache._make_key(item_name)
    assert key.startswith("name:toy:")
    assert "mystery object" in key


def test_cache_key_upc():
    """Cache key should use UPC when no ISBN available."""
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
        item = Item(name="Never Seen Before")
        assert cache.get(item) is None


def test_cache_ttl_expiration():
    """Expired cache entries should return None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = PriceCache(cache_dir=Path(tmpdir), ttl_days=0)  # 0 days = always expired

        item = Item(name="Stale Item")
        estimate = PriceEstimate(low=1.0, high=5.0, median=3.0, source="test")
        cache.put(item, estimate)

        # With 0-day TTL, should be expired immediately
        assert cache.get(item) is None


def test_enrich_price_uses_cache():
    """enrich_price should return cached result without hitting network."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Pre-populate cache
        cache = PriceCache(cache_dir=Path(tmpdir), ttl_days=1)
        item = Item(
            name="Blade Runner: The Director's Cut",
            category=ItemCategory.DVD,
            identifiers=Identifiers(upc="085391631729"),
        )
        estimate = PriceEstimate(low=4.0, high=12.0, median=7.50, source="ebay_completed")
        cache.put(item, estimate)

        # enrich_price should hit cache, not network
        enriched = enrich_price(item, use_cache=True, cache_dir=Path(tmpdir))
        assert enriched.pricing.median == 7.50
        assert enriched.pricing.source == "ebay_completed"
