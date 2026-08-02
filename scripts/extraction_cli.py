"""Standalone extraction CLI — Phase 0 offline prototype.

Usage:
    python -m scripts.extraction_cli --fixture create_001
    python -m scripts.extraction_cli --paste

Reads a conversation (from a labeled fixture or pasted text), runs the
extraction + temporal validation pipeline, and prints the resulting
SchedulingEvent JSON. No database, no WhatsApp connection.
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from backend.app.schemas.conversation import (
    ConversationWindow,
    ContactContext,
    Message,
    ProfessionalContext,
    UpcomingAppointment,
)
from backend.app.services.extraction import extract_scheduling_event
from backend.app.services.temporal import validate_temporal

FIXTURES_PATH = (
    Path(__file__).resolve().parents[1]
    / "backend"
    / "tests"
    / "fixtures"
    / "labeled_conversations.json"
)


def load_fixture(fixture_id: str) -> dict:
    """Load a single labeled fixture by ID."""
    with open(FIXTURES_PATH, encoding="utf-8") as f:
        fixtures = json.load(f)
    for fixture in fixtures:
        if fixture["id"] == fixture_id:
            return fixture
    raise ValueError(f"Fixture '{fixture_id}' not found in {FIXTURES_PATH}")


def fixture_to_conversation_window(fixture: dict) -> ConversationWindow:
    """Convert a labeled fixture dict into a ConversationWindow."""
    return ConversationWindow(
        professional=ProfessionalContext(**fixture["professional"]),
        contact=ContactContext(**fixture["contact"]),
        current_time=fixture["current_time"],
        upcoming_appointments=[
            UpcomingAppointment(**appt) for appt in fixture.get("upcoming_appointments", [])
        ],
        messages=[Message(**msg) for msg in fixture["messages"]],
    )


def build_window_from_pasted_text(text: str) -> ConversationWindow:
    """Build a minimal ConversationWindow from freeform pasted conversation text.

    Each line is treated as a message. Lines starting with '>' are outbound
    (professional), everything else is inbound (customer). Uses the current
    time as reference.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    messages = []
    for i, line in enumerate(text.strip().splitlines()):
        line = line.strip()
        if not line:
            continue
        direction = "outbound" if line.startswith(">") else "inbound"
        content = line.lstrip(">").strip()
        messages.append(
            Message(id=f"msg_{i}", direction=direction, sent_at=now, text=content)
        )

    return ConversationWindow(
        professional=ProfessionalContext(),
        contact=ContactContext(display_name="Cliente"),
        current_time=now,
        upcoming_appointments=[],
        messages=messages,
    )


def run_extraction(conversation_window: ConversationWindow) -> dict:
    """Run the full Phase 0 pipeline: extraction + temporal validation."""
    event = extract_scheduling_event(conversation_window)
    validated_event = validate_temporal(event, conversation_window)
    return validated_event.model_dump(mode="json")


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Phase 0 offline extraction CLI")
    parser.add_argument("--fixture", help="Fixture ID to run (see labeled_conversations.json)")
    parser.add_argument(
        "--paste",
        action="store_true",
        help="Read conversation from stdin (lines prefixed with '>' are outbound)",
    )
    args = parser.parse_args()

    if args.fixture:
        fixture = load_fixture(args.fixture)
        window = fixture_to_conversation_window(fixture)
    elif args.paste:
        print("Cole a conversa (linhas com '>' sao do profissional). Ctrl+D para finalizar:")
        text = sys.stdin.read()
        window = build_window_from_pasted_text(text)
    else:
        parser.print_help()
        sys.exit(1)

    result = run_extraction(window)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
