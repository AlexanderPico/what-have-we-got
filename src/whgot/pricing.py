"""Price lookup engine — fetch comparable sold prices from multiple sources.

Supports:
- eBay completed listings via Browse API (free, no auth for search)
- OpenLibrary for book metadata + ISBN enrichment
- Local SQLite cache with configurable TTL

All lookups are optional and fail gracefully — an item with no pricing
data is still a valid Item, just unenriched.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import httpx

from whgot.schema import Item, PriceEstimate

# --- Configuration ---

DEFAULT_CACHE_DIR = Path.home() / ".whgot"
CACHE_DB = "price_cache.db"
DEFAULT_TTL_DAYS = 7  # How long cached prices are considered fresh

# eBay Browse API (unauthenticated search — limited but free)
EBAY_SEARCH_URL = "https://www.ebay.com/sch/i.html"

# OpenLibrary API (free, no auth)
OPENLIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
OPENLIBRARY_ISBN_URL = "https://openlibrary.org/isbn/{isbn}.json"


# --- Cache Layer ---


class PriceCache:
    """SQLite-backed price cache with TTL expiration.

    Stores price lookups keyed by a normalized item identifier
    (name + category, or ISBN/UPC if available).
    """

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR, ttl_days: int = DEFAULT_TTL_DAYS):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / CACHE_DB
        self.ttl = timedelta(days=ttl_days)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prices (
                    cache_key TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    source TEXT NOT NULL,
                    fetched_at REAL NOT NULL
                )
            """)

    @staticmethod
    def _make_key(item: Item) -> str:
        """Generate a cache key from an item's most specific identifier."""
        if item.identifiers.isbn13:
            return f"isbn13:{item.identifiers.isbn13}"
        if item.identifiers.isbn:
            return f"isbn:{item.identifiers.isbn}"
        if item.identifiers.upc:
            return f"upc:{item.identifiers.upc}"
        if item.identifiers.asin:
            return f"asin:{item.identifiers.asin}"
        # Fall back to normalized name + category
        return f"name:{item.category.value}:{item.name.lower().strip()}"

    def get(self, item: Item) -> Optional[PriceEstimate]:
        """Retrieve cached price if fresh, else None."""
        key = self._make_key(item)
        cutoff = time.time() - self.ttl.total_seconds()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT data, source, fetched_at FROM prices WHERE cache_key = ? AND fetched_at > ?",
                (key, cutoff),
            ).fetchone()
        if row:
            data = json.loads(row[0])
            return PriceEstimate(
                low=data.get("low"),
                high=data.get("high"),
                median=data.get("median"),
                source=row[1],
                last_updated=datetime.fromtimestamp(row[2]),
            )
        return None

    def put(self, item: Item, estimate: PriceEstimate) -> None:
        """Store a price estimate in cache."""
        key = self._make_key(item)
        data = json.dumps({
            "low": estimate.low,
            "high": estimate.high,
            "median": estimate.median,
        })
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO prices (cache_key, data, source, fetched_at) VALUES (?, ?, ?, ?)",
                (key, data, estimate.source or "unknown", time.time()),
            )


# --- OpenLibrary Lookup ---


def _lookup_openlibrary(item: Item, client: httpx.Client) -> Optional[PriceEstimate]:
    """Look up book metadata from OpenLibrary. Returns None for non-books.

    Primarily useful for ISBN enrichment rather than pricing, but
    OpenLibrary sometimes has edition/format info that helps price estimation.
    """
    if item.identifiers.isbn or item.identifiers.isbn13:
        isbn = item.identifiers.isbn13 or item.identifiers.isbn
        try:
            resp = client.get(
                OPENLIBRARY_ISBN_URL.format(isbn=isbn),
                timeout=10,
                follow_redirects=True,
            )
            if resp.status_code == 200:
                data = resp.json()
                # Enrich metadata if we got useful data
                if "publishers" in data and not item.metadata.publisher:
                    pubs = data["publishers"]
                    if isinstance(pubs, list) and pubs:
                        item.metadata.publisher = pubs[0]
                if "publish_date" in data and not item.metadata.year_published:
                    try:
                        item.metadata.year_published = int(data["publish_date"][-4:])
                    except (ValueError, IndexError):
                        pass
        except Exception:
            pass  # OpenLibrary is optional enrichment

    # Search by title + author for books without ISBN
    if item.category.value == "book" and item.metadata.author:
        query = f"{item.name} {item.metadata.author}"
    elif item.category.value == "book":
        query = item.name
    else:
        return None

    try:
        resp = client.get(
            OPENLIBRARY_SEARCH_URL,
            params={"q": query, "limit": 1, "fields": "isbn,publisher,publish_year,edition_count"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            docs = data.get("docs", [])
            if docs:
                doc = docs[0]
                # Enrich ISBN if we don't have one
                if not item.identifiers.isbn and not item.identifiers.isbn13:
                    isbns = doc.get("isbn", [])
                    for i in isbns:
                        if len(i) == 13:
                            item.identifiers.isbn13 = i
                            break
                        elif len(i) == 10:
                            item.identifiers.isbn = i
                # Edition count can hint at demand/commonality
                edition_count = doc.get("edition_count", 0)
                if edition_count > 50:
                    # Very common book — likely low resale value
                    return PriceEstimate(low=1.0, high=8.0, median=3.0, source="openlibrary_heuristic")
                elif edition_count > 10:
                    return PriceEstimate(low=3.0, high=15.0, median=7.0, source="openlibrary_heuristic")
                elif edition_count > 0:
                    return PriceEstimate(low=5.0, high=30.0, median=12.0, source="openlibrary_heuristic")
    except Exception:
        pass

    return None


# --- eBay Scrape (completed listings heuristic) ---


def _build_ebay_search_url(item: Item) -> str:
    """Build an eBay completed listings search URL for an item."""
    query_parts = [item.name]
    if item.metadata.author:
        query_parts.append(item.metadata.author)
    if item.metadata.brand:
        query_parts.append(item.metadata.brand)
    if item.identifiers.isbn13 or item.identifiers.isbn:
        query_parts = [item.identifiers.isbn13 or item.identifiers.isbn]

    query = " ".join(query_parts)
    return f"{EBAY_SEARCH_URL}?_nkw={quote_plus(query)}&LH_Complete=1&LH_Sold=1&_sop=13"


def _lookup_ebay(item: Item, client: httpx.Client) -> Optional[PriceEstimate]:
    """Scrape eBay completed/sold listings for price comps.

    This is a best-effort scrape of eBay's search results page.
    Fragile by nature — eBay changes their HTML regularly.
    For production use, migrate to the eBay Browse API with OAuth.
    """
    import re

    url = _build_ebay_search_url(item)

    try:
        resp = client.get(
            url,
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return None

        # Extract prices from sold listings
        # Look for price patterns in the HTML — this is fragile but works for now
        html = resp.text
        # eBay sold prices typically appear as "$XX.XX" in specific contexts
        price_pattern = re.compile(r'\$(\d{1,5}\.\d{2})')
        prices = [float(m) for m in price_pattern.findall(html)]

        if not prices:
            return None

        # Filter out obvious outliers (shipping costs, very low/high values)
        prices = [p for p in prices if 0.99 <= p <= 9999.99]
        if not prices:
            return None

        # Take the first ~20 results (most recent sold)
        prices = prices[:20]
        prices.sort()

        return PriceEstimate(
            low=prices[0],
            high=prices[-1],
            median=prices[len(prices) // 2],
            source="ebay_completed",
            last_updated=datetime.now(),
        )

    except Exception:
        return None


# --- Public API ---


def enrich_price(
    item: Item,
    use_cache: bool = True,
    sources: Optional[list[str]] = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> Item:
    """Enrich an Item with pricing data from available sources.

    Checks cache first, then queries sources in order. First successful
    result wins and gets cached.

    Args:
        item: The Item to enrich.
        use_cache: Whether to check/update the local price cache.
        sources: List of sources to query. Default: ["openlibrary", "ebay"].
                 Order matters — first successful result is used.
        cache_dir: Directory for the SQLite price cache.

    Returns:
        The same Item, mutated with pricing data if found.
    """
    if sources is None:
        sources = ["openlibrary", "ebay"]

    cache = PriceCache(cache_dir=cache_dir) if use_cache else None

    # Check cache first
    if cache:
        cached = cache.get(item)
        if cached:
            item.pricing = cached
            return item

    # Query sources in order
    estimate: Optional[PriceEstimate] = None

    with httpx.Client() as client:
        for source in sources:
            if source == "openlibrary" and item.category.value == "book":
                estimate = _lookup_openlibrary(item, client)
            elif source == "ebay":
                estimate = _lookup_ebay(item, client)

            if estimate:
                break

    if estimate:
        item.pricing = estimate
        if cache:
            cache.put(item, estimate)

    return item


def enrich_prices(
    items: list[Item],
    use_cache: bool = True,
    sources: Optional[list[str]] = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> list[Item]:
    """Enrich a list of Items with pricing data. Convenience wrapper around enrich_price."""
    return [enrich_price(item, use_cache=use_cache, sources=sources, cache_dir=cache_dir) for item in items]
