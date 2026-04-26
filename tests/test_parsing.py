"""Parser regression tests using fixture payloads."""

from pathlib import Path

from whgot.parsing import parse_items_response
from whgot.schema import ItemCategory

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_single_book_fixture():
    raw = (FIXTURES / "vision" / "single-book-response.json.txt").read_text()
    items = parse_items_response(raw)
    assert len(items) == 1
    assert items[0].category == ItemCategory.BOOK
    assert items[0].metadata.author == "Hideo Nitta"


def test_parse_batch_fixture():
    raw = (FIXTURES / "vision" / "batch-shelf-response.json.txt").read_text()
    items = parse_items_response(raw)
    assert len(items) == 2
    assert items[1].category == ItemCategory.TOY
    assert items[1].metadata.in_packaging is True


def test_parse_markdown_fence_fixture():
    raw = (FIXTURES / "vision" / "malformed-response-markdown-fence.txt").read_text()
    items = parse_items_response(raw)
    assert len(items) == 1
    assert items[0].category == ItemCategory.ELECTRONICS
    assert items[0].metadata.model == "WM-FX195"
