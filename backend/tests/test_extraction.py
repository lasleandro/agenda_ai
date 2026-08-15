"""Regression tests for the scheduling extraction pipeline.

Runs each labeled fixture through the extraction + temporal validation
pipeline and asserts the operation and confirmation status match. Requires
the Azure OpenAI connector credentials — these are integration tests, not unit
tests, since extraction depends on a live LLM call.
"""

import json
import os
from pathlib import Path

import pytest

from scripts.extraction_cli import fixture_to_conversation_window, run_extraction

FIXTURES_PATH = Path(__file__).resolve().parent / "fixtures" / "labeled_conversations.json"


def load_fixtures() -> list[dict]:
    with open(FIXTURES_PATH, encoding="utf-8") as f:
        return json.load(f)


requires_azure_openai = pytest.mark.skipif(
    not (os.getenv("AZURE_OPENAI_API_KEY") and os.getenv("AZURE_OPENAI_ENDPOINT")),
    reason="Azure OpenAI credentials not set — skipping live extraction tests",
)


@requires_azure_openai
@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda fx: fx["id"])
def test_extraction_matches_expected_operation_and_confirmation_status(fixture):
    window = fixture_to_conversation_window(fixture)
    result = run_extraction(window)
    assert result["operation"] == fixture["expected_operation"], (
        f"{fixture['id']}: expected operation={fixture['expected_operation']}, "
        f"got {result['operation']} (explanation: {result.get('explanation')})"
    )
    assert result["confirmation_status"] == fixture["expected_confirmation_status"], (
        f"{fixture['id']}: expected confirmation_status="
        f"{fixture['expected_confirmation_status']}, "
        f"got {result['confirmation_status']} (explanation: {result.get('explanation')})"
    )
