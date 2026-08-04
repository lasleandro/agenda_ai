"""Regression test + confidence calibration against the labeled dataset.

Runs every fixture in labeled_conversations.json through the extraction
pipeline, compares actual vs. expected, and reports:
  - accuracy per category (action match, temporal match)
  - a confidence-vs-correctness table to calibrate the thresholds in
    brief Section 15 (0.90 / 0.70 defaults).

Usage:
    python -m scripts.calibrate
"""

import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from scripts.extraction_cli import (
    FIXTURES_PATH,
    fixture_to_conversation_window,
    run_extraction,
)


def _parse_expected_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def evaluate_fixture(fixture: dict) -> dict:
    """Run one fixture and compare actual vs expected."""
    window = fixture_to_conversation_window(fixture)
    result = run_extraction(window)

    action_correct = result["action"] == fixture["expected_action"]

    # Temporal correctness: skip for cancel/none actions where start_at is not meaningful.
    expected_action = fixture["expected_action"]
    if expected_action in ("cancel", "none"):
        temporal_correct = True  # temporal not applicable — only action matters
    else:
        expected_start = _parse_expected_dt(fixture.get("expected_start_at"))
        actual_start = _parse_expected_dt(result.get("start_at"))
        if expected_start is None and actual_start is None:
            temporal_correct = True
        elif expected_start is None or actual_start is None:
            temporal_correct = False
        else:
            temporal_correct = expected_start == actual_start

    overall_correct = action_correct and temporal_correct

    return {
        "id": fixture["id"],
        "category": fixture["category"],
        "confidence": result["confidence"],
        "action_correct": action_correct,
        "temporal_correct": temporal_correct,
        "overall_correct": overall_correct,
        "expected_action": fixture["expected_action"],
        "actual_action": result["action"],
    }


def main():
    load_dotenv()

    with open(FIXTURES_PATH, encoding="utf-8") as f:
        fixtures = json.load(f)

    results = [evaluate_fixture(fx) for fx in fixtures]

    total = len(results)
    correct = sum(r["overall_correct"] for r in results)
    print(f"Overall accuracy: {correct}/{total} ({100 * correct / total:.1f}%)\n")

    # Per-category breakdown
    categories = sorted({r["category"] for r in results})
    print("Per-category accuracy:")
    for cat in categories:
        cat_results = [r for r in results if r["category"] == cat]
        cat_correct = sum(r["overall_correct"] for r in cat_results)
        print(f"  {cat}: {cat_correct}/{len(cat_results)}")

    # Confidence calibration: bucket by confidence range, check actual correctness
    print("\nConfidence calibration (predicted confidence vs actual correctness):")
    buckets = [(0.9, 1.01), (0.7, 0.9), (0.0, 0.7)]
    for low, high in buckets:
        bucket_results = [r for r in results if low <= r["confidence"] < high]
        if not bucket_results:
            print(f"  [{low:.2f}-{high:.2f}): no samples")
            continue
        bucket_correct = sum(r["overall_correct"] for r in bucket_results)
        actual_accuracy = 100 * bucket_correct / len(bucket_results)
        print(
            f"  [{low:.2f}-{high:.2f}): {bucket_correct}/{len(bucket_results)} "
            f"correct ({actual_accuracy:.1f}% actual accuracy)"
        )

    print(
        "\nNOTE: per brief Section 15, adjust high_confidence/medium_confidence "
        "thresholds to match the ACTUAL accuracy observed above, not the raw "
        "model-reported confidence score."
    )

    # Print failures for debugging
    failures = [r for r in results if not r["overall_correct"]]
    if failures:
        print(f"\nFailures ({len(failures)}):")
        for r in failures:
            print(
                f"  {r['id']}: expected={r['expected_action']} "
                f"actual={r['actual_action']} confidence={r['confidence']:.2f}"
            )


if __name__ == "__main__":
    main()
