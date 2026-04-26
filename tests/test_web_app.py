"""Web app tests."""

from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from whgot.schema import Item, ItemCategory, ItemMetadata, PriceEstimate
from whgot.web_app import app

client = TestClient(app)


def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_page_loads():
    response = client.get("/")
    assert response.status_code == 200
    assert "Analyze items" in response.text


def test_session_index_page(tmp_path: Path):
    import whgot.web_app as web_app

    web_app.store = web_app.SessionStore(root=tmp_path)
    session_id, _ = web_app.store.create_session_dir()
    item = Item(name="Saved Session Item", category=ItemCategory.BOOK)
    item = web_app.assess_items([item])[0]
    listings = web_app.generate_listings([item], use_llm=False)
    web_app.store.save_bundle(
        session_id,
        items=[item],
        listings=listings,
        metadata={"mode": "single", "model": "test-model"},
    )

    response = client.get("/sessions")
    assert response.status_code == 200
    assert session_id in response.text


def test_analyze_text_flow(monkeypatch, tmp_path: Path):
    import whgot.web_app as web_app

    web_app.store = web_app.SessionStore(root=tmp_path)

    def fake_identify_text(description: str, model: str):
        return Item(
            name=description,
            category=ItemCategory.BOOK,
            confidence=0.8,
            metadata=ItemMetadata(author="Author"),
        )

    def fake_enrich_prices(items):
        items[0].pricing = PriceEstimate(
            low=10.0,
            high=20.0,
            median=15.0,
            source="test_source",
            comp_count=4,
            source_details=["mock-source-detail"],
        )
        return items

    monkeypatch.setattr(web_app, "identify_text", fake_identify_text)
    monkeypatch.setattr(web_app, "enrich_prices", fake_enrich_prices)

    response = client.post(
        "/analyze",
        data={
            "mode": "single",
            "model": "test-model",
            "text_input": "The Manga Guide to Relativity",
            "price_lookup": "on",
        },
    )
    assert response.status_code == 200
    assert "The Manga Guide to Relativity" in response.text
    assert "test_source" in response.text
    assert "mock-source-detail" in response.text


def test_analyze_upload_flow(monkeypatch, tmp_path: Path):
    import whgot.web_app as web_app

    web_app.store = web_app.SessionStore(root=tmp_path)
    monkeypatch.setattr(
        web_app,
        "identify_image",
        lambda path, model, batch_mode: [
            Item(name="Uploaded Item", category=ItemCategory.ELECTRONICS, confidence=0.7)
        ],
    )
    monkeypatch.setattr(web_app, "enrich_prices", lambda items: items)

    response = client.post(
        "/analyze",
        data={"mode": "batch", "model": "test-model"},
        files={"files": ("sample.jpg", BytesIO(b"fake-image"), "image/jpeg")},
    )
    assert response.status_code == 200
    assert "Uploaded Item" in response.text


def test_missing_session_returns_404(tmp_path: Path):
    import whgot.web_app as web_app

    web_app.store = web_app.SessionStore(root=tmp_path)
    response = client.get("/sessions/does-not-exist")
    assert response.status_code == 404


def test_duplicate_upload_names_are_preserved(monkeypatch, tmp_path: Path):
    import whgot.web_app as web_app

    web_app.store = web_app.SessionStore(root=tmp_path)
    monkeypatch.setattr(
        web_app,
        "identify_image",
        lambda path, model, batch_mode: [
            Item(name=path.name, category=ItemCategory.ELECTRONICS, confidence=0.7)
        ],
    )
    monkeypatch.setattr(web_app, "enrich_prices", lambda items: items)

    response = client.post(
        "/analyze",
        data={"mode": "batch", "model": "test-model"},
        files=[
            ("files", ("same.jpg", BytesIO(b"first-image"), "image/jpeg")),
            ("files", ("same.jpg", BytesIO(b"second-image"), "image/jpeg")),
        ],
    )

    assert response.status_code == 200
    session_dirs = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(session_dirs) == 1
    uploads = list((session_dirs[0] / "uploads").iterdir())
    assert len(uploads) == 2
    assert len({upload.name for upload in uploads}) == 2


def test_session_results_filters_and_sorting(tmp_path: Path):
    import whgot.web_app as web_app

    web_app.store = web_app.SessionStore(root=tmp_path)
    session_id, _ = web_app.store.create_session_dir()

    book = Item(name="Book Item", category=ItemCategory.BOOK, confidence=0.9)
    toy = Item(name="Toy Item", category=ItemCategory.TOY, confidence=0.4)
    book.pricing = PriceEstimate(median=25.0, source="source-a")
    items = web_app.assess_items([book, toy])
    listings = web_app.generate_listings(items, use_llm=False)
    web_app.store.save_bundle(
        session_id,
        items=items,
        listings=listings,
        metadata={"mode": "batch", "model": "test-model"},
    )

    response = client.get(
        f"/sessions/{session_id}?category_filter=book&priced_only=true&sort_by=price"
    )
    assert response.status_code == 200
    assert "Book Item" in response.text
    assert "Toy Item" not in response.text
    assert "Visible item details" in response.text
