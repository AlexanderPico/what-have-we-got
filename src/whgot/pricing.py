"""Price lookup engine — fetch comparable sold prices from free/public sources.

Supports:
- eBay completed listings via heuristic HTML scrape
- OpenLibrary metadata + commonness heuristics for books
- Local SQLite cache with configurable TTL

All lookups are optional and fail gracefully.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import httpx

from whgot.schema import Item, PriceEstimate

DEFAULT_CACHE_DIR = Path.home() / ".whgot"
CACHE_DB = "price_cache.db"
DEFAULT_TTL_DAYS = 7

EBAY_SEARCH_URL = "https://www.ebay.com/sch/i.html"
OPENLIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
OPENLIBRARY_ISBN_URL = "https://openlibrary.org/isbn/{isbn}.json"


class PriceCache:
    """SQLite-backed price cache with TTL expiration."""

    def __init__(
        self,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        ttl_days: int = DEFAULT_TTL_DAYS,
    ):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / CACHE_DB
        self.ttl = timedelta(days=ttl_days)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prices (
                    cache_key TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    source TEXT NOT NULL,
                    fetched_at REAL NOT NULL
                )
                """
            )

    @staticmethod
    def _make_key(item: Item) -> str:
        if item.identifiers.isbn13:
            return f"isbn13:{item.identifiers.isbn13}"
        if item.identifiers.isbn:
            return f"isbn:{item.identifiers.isbn}"
        if item.identifiers.upc:
            return f"upc:{item.identifiers.upc}"
        if item.identifiers.asin:
            return f"asin:{item.identifiers.asin}"
        return f"name:{item.category.value}:{item.name.lower().strip()}"

    def get(self, item: Item) -> Optional[PriceEstimate]:
        key = self._make_key(item)
        cutoff = time.time() - self.ttl.total_seconds()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                (
                    "SELECT data, source, fetched_at FROM prices "
                    "WHERE cache_key = ? AND fetched_at > ?"
                ),
                (key, cutoff),
            ).fetchone()
        if not row:
            return None

        data = json.loads(row[0])
        return PriceEstimate(
            low=data.get("low"),
            high=data.get("high"),
            median=data.get("median"),
            source=row[1],
            last_updated=datetime.fromtimestamp(row[2]),
            comp_count=data.get("comp_count"),
            query=data.get("query"),
            source_details=data.get("source_details", []),
            confidence=data.get("confidence"),
            warning=data.get("warning"),
        )

    def put(self, item: Item, estimate: PriceEstimate) -> None:
        key = self._make_key(item)
        data = json.dumps(
            {
                "low": estimate.low,
                "high": estimate.high,
                "median": estimate.median,
                "comp_count": estimate.comp_count,
                "query": estimate.query,
                "source_details": estimate.source_details,
                "confidence": estimate.confidence,
                "warning": estimate.warning,
            }
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                (
                    "INSERT OR REPLACE INTO prices "
                    "(cache_key, data, source, fetched_at) VALUES (?, ?, ?, ?)"
                ),
                (key, data, estimate.source or "unknown", time.time()),
            )


def _estimate_from_prices(
    prices: list[float],
    *,
    source: str,
    query: str,
    source_details: list[str],
    warning: Optional[str] = None,
) -> Optional[PriceEstimate]:
    if not prices:
        return None

    prices = sorted(price for price in prices if 0.99 <= price <= 9999.99)
    if not prices:
        return None

    if len(prices) % 2:
        median = prices[len(prices) // 2]
    else:
        left = prices[len(prices) // 2 - 1]
        right = prices[len(prices) // 2]
        median = (left + right) / 2

    confidence = min(0.95, 0.35 + (len(prices) * 0.03))
    return PriceEstimate(
        low=prices[0],
        high=prices[-1],
        median=median,
        source=source,
        last_updated=datetime.now(),
        comp_count=len(prices),
        query=query,
        source_details=source_details,
        confidence=round(confidence, 2),
        warning=warning,
    )


def _lookup_openlibrary(item: Item, client: httpx.Client) -> Optional[PriceEstimate]:
    if item.identifiers.isbn or item.identifiers.isbn13:
        isbn = item.identifiers.isbn13 or item.identifiers.isbn
        try:
            response = client.get(
                OPENLIBRARY_ISBN_URL.format(isbn=isbn),
                timeout=10,
                follow_redirects=True,
            )
            if response.status_code == 200:
                data = response.json()
                publishers = data.get("publishers") or []
                if publishers and not item.metadata.publisher:
                    item.metadata.publisher = publishers[0]
                publish_date = data.get("publish_date")
                if publish_date and not item.metadata.year_published:
                    try:
                        item.metadata.year_published = int(str(publish_date)[-4:])
                    except (TypeError, ValueError):
                        pass
        except Exception:
            pass

    if item.category.value != "book":
        return None

    query = item.name
    if item.metadata.author:
        query = f"{item.name} {item.metadata.author}"

    try:
        response = client.get(
            OPENLIBRARY_SEARCH_URL,
            params={
                "q": query,
                "limit": 1,
                "fields": "isbn,publisher,publish_year,edition_count",
            },
            timeout=10,
        )
        if response.status_code != 200:
            return None
        data = response.json()
        docs = data.get("docs", [])
        if not docs:
            return None

        doc = docs[0]
        if not item.identifiers.isbn and not item.identifiers.isbn13:
            for isbn in doc.get("isbn", []):
                if len(isbn) == 13:
                    item.identifiers.isbn13 = isbn
                    break
                if len(isbn) == 10:
                    item.identifiers.isbn = isbn

        edition_count = int(doc.get("edition_count", 0) or 0)
        if edition_count > 50:
            prices = [1.0, 3.0, 8.0]
        elif edition_count > 10:
            prices = [3.0, 7.0, 15.0]
        elif edition_count > 0:
            prices = [5.0, 12.0, 30.0]
        else:
            return None

        return _estimate_from_prices(
            prices,
            source="openlibrary_heuristic",
            query=query,
            source_details=[
                "OpenLibrary search metadata",
                f"edition_count={edition_count}",
            ],
            warning="Heuristic estimate based on OpenLibrary edition frequency.",
        )
    except Exception:
        return None


def _build_ebay_search_query(item: Item) -> str:
    query_parts = [item.name]
    if item.metadata.author:
        query_parts.append(item.metadata.author)
    if item.metadata.brand:
        query_parts.append(item.metadata.brand)
    if item.identifiers.isbn13 or item.identifiers.isbn:
        query_parts = [item.identifiers.isbn13 or item.identifiers.isbn]
    return " ".join(query_parts)


def _build_ebay_search_url(item: Item) -> str:
    query = _build_ebay_search_query(item)
    return (
        f"{EBAY_SEARCH_URL}?_nkw={quote_plus(query)}"
        "&LH_Complete=1&LH_Sold=1&_sop=13"
    )


def _lookup_ebay(item: Item, client: httpx.Client) -> Optional[PriceEstimate]:
    url = _build_ebay_search_url(item)
    query = _build_ebay_search_query(item)
    try:
        response = client.get(
            url,
            timeout=15,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
        )
        if response.status_code != 200:
            return None

        prices = [float(match) for match in re.findall(r"\$(\d{1,5}\.\d{2})", response.text)]
        prices = prices[:20]
        return _estimate_from_prices(
            prices,
            source="ebay_completed",
            query=query,
            source_details=[url, f"price_count={len(prices)}"],
            warning="Heuristic estimate from eBay completed-listing HTML scrape.",
        )
    except Exception:
        return None


def enrich_price(
    item: Item,
    use_cache: bool = True,
    sources: Optional[list[str]] = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> Item:
    """Enrich an Item with pricing data from available sources."""
    if sources is None:
        sources = ["openlibrary", "ebay"]

    cache = PriceCache(cache_dir=cache_dir) if use_cache else None

    if cache:
        cached = cache.get(item)
        if cached:
            item.pricing = cached
            return item

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
    """Enrich a list of Items with pricing data."""
    return [
        enrich_price(item, use_cache=use_cache, sources=sources, cache_dir=cache_dir)
        for item in items
    ]
