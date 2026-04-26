"""Tests for eval manifest loading and scoring."""

import json
from pathlib import Path

from typer.testing import CliRunner

from whgot.cli import app
from whgot.eval import (
    evaluate_manifest_results,
    load_manifest,
    score_item,
    summarize_results,
    write_eval_report,
)
from whgot.schema import Item, ItemCategory, ItemMetadata

runner = CliRunner()


def test_load_manifest(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps([{"id": "sample-1"}]))
    manifest = load_manifest(manifest_path)
    assert manifest[0]["id"] == "sample-1"


def test_score_item_and_summary():
    benchmark = {
        "id": "book-1",
        "expected_name": "The Manga Guide to Relativity",
        "acceptable_aliases": ["Manga Guide to Relativity"],
        "expected_category": "book",
        "expected_key_metadata": {"author": "Hideo Nitta"},
    }
    item = Item(
        name="The Manga Guide to Relativity",
        category=ItemCategory.BOOK,
        metadata=ItemMetadata(author="Hideo Nitta"),
    )

    result = score_item(benchmark, item)
    summary = summarize_results([result])

    assert result.category_match is True
    assert result.name_match is True
    assert summary.category_accuracy == 1.0
    assert summary.metadata_hit_rate == 1.0


def test_evaluate_manifest_results_and_write_report(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    predictions_path = tmp_path / "predictions.json"
    report_path = tmp_path / "report.json"

    manifest_path.write_text(
        json.dumps(
            [
                {
                    "id": "book-1",
                    "expected_name": "The Manga Guide to Relativity",
                    "expected_category": "book",
                    "expected_key_metadata": {"author": "Hideo Nitta"},
                    "acceptable_aliases": ["Manga Guide to Relativity"],
                }
            ]
        )
    )
    predictions_path.write_text(
        json.dumps(
            [
                {
                    "name": "The Manga Guide to Relativity",
                    "category": "book",
                    "metadata": {"author": "Hideo Nitta"},
                }
            ]
        )
    )

    results, summary = evaluate_manifest_results(manifest_path, predictions_path)
    write_eval_report(results, summary, report_path)

    payload = json.loads(report_path.read_text())
    assert payload["summary"]["total"] == 1
    assert payload["results"][0]["benchmark_id"] == "book-1"


def test_eval_report_cli(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    predictions_path = tmp_path / "predictions.json"
    report_path = tmp_path / "report.json"

    manifest_path.write_text(
        json.dumps(
            [
                {
                    "id": "electronics-1",
                    "expected_name": "Sony Walkman WM-FX195",
                    "expected_category": "electronics",
                    "expected_key_metadata": {"model": "WM-FX195"},
                }
            ]
        )
    )
    predictions_path.write_text(
        json.dumps(
            [
                {
                    "name": "Sony Walkman WM-FX195",
                    "category": "electronics",
                    "metadata": {"model": "WM-FX195"},
                }
            ]
        )
    )

    result = runner.invoke(
        app,
        ["eval-report", str(manifest_path), str(predictions_path), "-o", str(report_path)],
    )
    assert result.exit_code == 0
    assert report_path.exists()
    assert "Eval Summary" in result.stdout
