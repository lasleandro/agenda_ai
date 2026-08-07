"""Unit tests for the context supplied to the scheduling extractor."""

from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.conversation import Message
from app.chat.prompt import build_conversation_text


def test_build_conversation_text_includes_local_date_and_time() -> None:
    """Give the LLM enough timestamp context for relative-date interpretation."""
    messages = [
        Message(
            id="message-1",
            direction="inbound",
            sent_at=datetime(2026, 8, 4, 23, 31, tzinfo=timezone.utc),
            text="E terça da semana que vem, rola 12h?",
        )
    ]

    text = build_conversation_text(messages, "America/Sao_Paulo")

    assert "04/08/2026 20:31" in text
    assert "E terça da semana que vem, rola 12h?" in text
