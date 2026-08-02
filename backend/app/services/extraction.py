"""LLM extraction service — wires Instructor + Anthropic to the SchedulingEvent schema.

Uses Instructor to enforce structured output from the LLM response.
"""

import anthropic
import instructor
from langfuse import Langfuse

from backend.app.schemas.conversation import ConversationWindow
from backend.app.schemas.extraction import SchedulingEvent
from backend.app.services.prompt import build_extraction_prompt


def get_langfuse_client() -> Langfuse | None:
    """Initialize Langfuse client if credentials are available."""
    import os

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

    if public_key and secret_key:
        return Langfuse(public_key=public_key, secret_key=secret_key, host=host)
    return None


def extract_scheduling_event(
    conversation_window: ConversationWindow,
    *,
    model: str = "claude-sonnet-4-20250514",
    prompt_version: str = "v0.1",
) -> SchedulingEvent:
    """Extract a structured scheduling event from a conversation window.

    Uses Instructor to enforce the SchedulingEvent Pydantic schema on the LLM output.
    Traces the call via Langfuse when credentials are available.

    Args:
        conversation_window: normalized conversation context.
        model: Anthropic model identifier.
        prompt_version: version tag for tracing and regression tracking.

    Returns:
        SchedulingEvent with the extracted scheduling action.
    """
    langfuse = get_langfuse_client()

    # Build prompts
    system_prompt, user_prompt = build_extraction_prompt(conversation_window)

    # Create Instructor-wrapped Anthropic client
    client = instructor.from_anthropic(
        anthropic.Anthropic(),
        mode=instructor.Mode.ANTHROPIC_JSON,
    )

    # Trace with Langfuse if available
    generation = None
    if langfuse:
        generation = langfuse.generation(
            name="extract_scheduling_event",
            model=model,
            input={"system": system_prompt, "user": user_prompt},
            metadata={"prompt_version": prompt_version},
        )

    try:
        event = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            response_model=SchedulingEvent,
        )

        # Log success to Langfuse
        if generation:
            generation.end(
                output=event.model_dump(),
                metadata={"status": "success"},
            )

        return event

    except Exception as e:
        if generation:
            generation.end(
                output={"error": str(e)},
                metadata={"status": "error"},
            )
        raise


def extract_scheduling_event_raw(
    conversation_window: ConversationWindow,
    *,
    model: str = "claude-sonnet-4-20250514",
) -> dict:
    """Extract and return as raw dict (useful for CLI/debugging)."""
    event = extract_scheduling_event(conversation_window, model=model)
    return event.model_dump()
