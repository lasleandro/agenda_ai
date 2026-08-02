"""Regression tests for the scheduling extraction pipeline.

Runs each labeled fixture through the extraction + temporal validation
pipeline and asserts the action matches. Requires an LLM API key to be set
(ANTHROPIC_API_KEY) — these are integration tests, not unit tests, since the
extraction depends on a live LLM call per brief Section 27 exit criteria.
"""

import json
import os
from pathlib import Path

import pytest

from scripts.extraction_cli import fixture_to_conversation_window, run_extraction

FIXTURES_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "labeled_conversations.json"
)


def load_fixtures() -> list[dict]:
    with open(FIXTURES_PATH, encoding="utf-8") as f:
        return json.load(f)


requires_llm = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — skipping live extraction tests",
)


@requires_llm
@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda fx: fx["id"])
def test_extraction_matches_expected_action(fixture):
    window = fixture_to_conversation_window(fixture)
    result = run_extraction(window)
    assert result["action"] == fixture["expected_action"], (
        f"{fixture['id']}: expected action={fixture['expected_action']}, "
        f"got {result['action']} (explanation: {result.get('explanation')})"
    )
