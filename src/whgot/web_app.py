"""Local FastAPI web app for whgot."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from whgot.listing import generate_listings
from whgot.pricing import enrich_prices
from whgot.schema import Item
from whgot.session_store import SessionNotFoundError, SessionStore
from whgot.triage import assess_items
from whgot.vision import DEFAULT_MODEL, identify_image, identify_text

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "web_templates"
STATIC_DIR = BASE_DIR / "web_static"

app = FastAPI(title="whgot")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
store = SessionStore()


def _serialize_items(items: list[Item]) -> list[dict]:
    return [item.model_dump(mode="json", exclude_none=True) for item in items]


def _unique_upload_destination(uploads_dir: Path, filename: str) -> Path:
    original = Path(filename).name or "upload.bin"
    candidate = uploads_dir / original
    if not candidate.exists():
        return candidate

    stem = Path(original).stem or "upload"
    suffix = Path(original).suffix
    return uploads_dir / f"{stem}-{uuid4().hex[:8]}{suffix}"


def _load_bundle_or_404(session_id: str) -> dict:
    try:
        return store.load_bundle(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _process_uploads(
    session_dir: Path,
    uploads: list[UploadFile],
    *,
    model: str,
    batch_mode: bool,
) -> list[Item]:
    items: list[Item] = []
    uploads_dir = session_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    for upload in uploads:
        if not upload.filename:
            continue
        destination = _unique_upload_destination(uploads_dir, upload.filename)
        with destination.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)
        items.extend(identify_image(destination, model=model, batch_mode=batch_mode))

    return items


def _process_text(text_input: str, model: str) -> list[Item]:
    items: list[Item] = []
    lines = [line.strip() for line in text_input.splitlines() if line.strip()]
    for line in lines:
        items.append(identify_text(line, model=model))
    return items


def _prepare_item_views(items: list[dict]) -> list[dict]:
    views: list[dict] = []
    for item in items:
        pricing = item.get("pricing", {})
        triage = item.get("triage", {})
        reasons = triage.get("reasons", [])
        price_value = pricing.get("median")
        if price_value is None:
            price_value = pricing.get("high") or pricing.get("low") or 0.0
        triage_reason_text = "; ".join(reasons) if reasons else "No triage reasons recorded."
        provenance_text = "; ".join(pricing.get("source_details", []))
        if not provenance_text:
            provenance_text = "No source details recorded."
        views.append(
            {
                **item,
                "sort_price": float(price_value or 0.0),
                "sort_confidence": float(item.get("confidence") or 0.0),
                "sort_triage": float(triage.get("score") or 0.0),
                "triage_reason_text": triage_reason_text,
                "provenance_text": provenance_text,
            }
        )
    return views


def _sort_item_views(item_views: list[dict], sort_by: str) -> list[dict]:
    key_map = {
        "price": "sort_price",
        "confidence": "sort_confidence",
        "name": "name",
        "triage": "sort_triage",
    }
    key = key_map.get(sort_by, "sort_triage")
    reverse = key != "name"
    return sorted(item_views, key=lambda item: item.get(key) or 0, reverse=reverse)


def _build_context(
    bundle: dict,
    *,
    sort_by: str = "triage",
    category_filter: str = "all",
    priced_only: bool = False,
) -> dict:
    items = bundle.get("items", [])
    listings = bundle.get("listings", [])
    priced_count = sum(1 for item in items if item.get("pricing", {}).get("median"))

    item_views = _prepare_item_views(items)
    if category_filter != "all":
        item_views = [item for item in item_views if item.get("category") == category_filter]
    if priced_only:
        item_views = [item for item in item_views if item.get("pricing", {}).get("median")]
    item_views = _sort_item_views(item_views, sort_by)

    visible_names = {item.get("name") for item in item_views}
    visible_listings = [
        listing
        for listing in listings
        if listing.get("source_item_name") in visible_names
    ]
    if not visible_names:
        visible_listings = []

    return {
        "session_id": bundle["session_id"],
        "saved_at": bundle.get("saved_at"),
        "metadata": bundle.get("metadata", {}),
        "items": item_views,
        "listings": visible_listings,
        "total_items": len(items),
        "visible_items": len(item_views),
        "priced_count": priced_count,
        "sort_by": sort_by,
        "category_filter": category_filter,
        "priced_only": priced_only,
        "available_categories": sorted({item.get("category", "other") for item in items}),
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "model": DEFAULT_MODEL,
            "recent_sessions": store.list_sessions()[:10],
        },
    )


@app.get("/sessions", response_class=HTMLResponse)
def session_index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "sessions.html",
        {"sessions": store.list_sessions()},
    )


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(
    request: Request,
    mode: str = Form("single"),
    model: str = Form(DEFAULT_MODEL),
    price_lookup: Optional[str] = Form(None),
    use_llm: Optional[str] = Form(None),
    text_input: str = Form(""),
    files: list[UploadFile] = File(default_factory=list),
) -> HTMLResponse:
    session_id, session_dir = store.create_session_dir()

    items: list[Item] = []
    if text_input.strip():
        items.extend(_process_text(text_input, model=model))
    if files:
        items.extend(
            _process_uploads(
                session_dir,
                files,
                model=model,
                batch_mode=(mode == "batch"),
            )
        )

    if price_lookup:
        items = enrich_prices(items)

    items = assess_items(items)
    listings = generate_listings(items, use_llm=bool(use_llm), model=model)

    metadata = {
        "mode": mode,
        "model": model,
        "price_lookup": bool(price_lookup),
        "use_llm": bool(use_llm),
    }
    store.save_bundle(session_id, items=items, listings=listings, metadata=metadata)
    bundle = store.load_bundle(session_id)
    return templates.TemplateResponse(request, "results.html", _build_context(bundle))


@app.get("/sessions/{session_id}", response_class=HTMLResponse)
def session_results(
    request: Request,
    session_id: str,
    sort_by: str = "triage",
    category_filter: str = "all",
    priced_only: bool = False,
) -> HTMLResponse:
    bundle = _load_bundle_or_404(session_id)
    return templates.TemplateResponse(
        request,
        "results.html",
        _build_context(
            bundle,
            sort_by=sort_by,
            category_filter=category_filter,
            priced_only=priced_only,
        ),
    )


@app.get("/sessions/{session_id}/export.json")
def export_json(session_id: str) -> FileResponse:
    _load_bundle_or_404(session_id)
    path = store.session_dir(session_id) / "session.json"
    return FileResponse(path, filename=f"{session_id}.json", media_type="application/json")


@app.get("/sessions/{session_id}/export.csv")
def export_csv(session_id: str) -> FileResponse:
    _load_bundle_or_404(session_id)
    path = store.session_dir(session_id) / "items.csv"
    return FileResponse(path, filename=f"{session_id}.csv", media_type="text/csv")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/sessions/{session_id}/raw")
def raw_bundle(session_id: str) -> dict:
    return _load_bundle_or_404(session_id)


@app.post("/demo-load")
def demo_load() -> RedirectResponse:
    session_id, _session_dir = store.create_session_dir()
    demo_item = Item(name="Demo Item")
    demo_item = assess_items([demo_item])[0]
    demo_listings = generate_listings([demo_item], use_llm=False)
    store.save_bundle(
        session_id,
        items=[demo_item],
        listings=demo_listings,
        metadata={"mode": "demo", "model": "none", "price_lookup": False, "use_llm": False},
    )
    return RedirectResponse(url=f"/sessions/{session_id}", status_code=303)


def run() -> None:
    uvicorn.run("whgot.web_app:app", host="127.0.0.1", port=8000, reload=False)
