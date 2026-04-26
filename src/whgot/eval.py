"""Benchmark manifest loading and scoring helpers for whgot eval runs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from whgot.schema import Item


@dataclass
class EvalResult:
    benchmark_id: str
    category_match: bool
    name_match: bool
    metadata_hits: int
    metadata_total: int


@dataclass
class EvalSummary:
    total: int
    category_accuracy: float
    name_accuracy: float
    metadata_hit_rate: float


def load_manifest(path: str | Path) -> list[dict[str, Any]]:
    return json.loads(Path(path).read_text())


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def score_item(benchmark: dict[str, Any], item: Item) -> EvalResult:
    expected_name = _normalize(benchmark.get("expected_name"))
    aliases = {_normalize(alias) for alias in benchmark.get("acceptable_aliases", [])}
    observed_name = _normalize(item.name)

    name_match = observed_name == expected_name or observed_name in aliases
    category_match = item.category.value == benchmark.get("expected_category", "other")

    expected_metadata = benchmark.get("expected_key_metadata", {})
    hits = 0
    total = len(expected_metadata)
    for key, expected in expected_metadata.items():
        if _normalize(str(getattr(item.metadata, key, ""))) == _normalize(str(expected)):
            hits += 1

    return EvalResult(
        benchmark_id=str(benchmark.get("id", "unknown")),
        category_match=category_match,
        name_match=name_match,
        metadata_hits=hits,
        metadata_total=total,
    )


def summarize_results(results: list[EvalResult]) -> EvalSummary:
    if not results:
        return EvalSummary(total=0, category_accuracy=0.0, name_accuracy=0.0, metadata_hit_rate=0.0)

    total = len(results)
    category_accuracy = sum(result.category_match for result in results) / total
    name_accuracy = sum(result.name_match for result in results) / total
    metadata_hits = sum(result.metadata_hits for result in results)
    metadata_total = sum(result.metadata_total for result in results)
    metadata_hit_rate = metadata_hits / metadata_total if metadata_total else 0.0

    return EvalSummary(
        total=total,
        category_accuracy=round(category_accuracy, 4),
        name_accuracy=round(name_accuracy, 4),
        metadata_hit_rate=round(metadata_hit_rate, 4),
    )


def evaluate_manifest_results(
    manifest_path: str | Path,
    predictions_path: str | Path,
) -> tuple[list[EvalResult], EvalSummary]:
    manifest = load_manifest(manifest_path)
    predictions_raw = json.loads(Path(predictions_path).read_text())
    predictions = [Item(**entry) for entry in predictions_raw]

    if len(manifest) != len(predictions):
        raise ValueError(
            "Manifest/prediction length mismatch: "
            f"{len(manifest)} benchmarks vs {len(predictions)} predictions"
        )

    results = [score_item(benchmark, item) for benchmark, item in zip(manifest, predictions)]
    return results, summarize_results(results)


def write_eval_report(
    results: list[EvalResult],
    summary: EvalSummary,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    payload = {
        "summary": asdict(summary),
        "results": [asdict(result) for result in results],
    }
    path.write_text(json.dumps(payload, indent=2))
    return path
