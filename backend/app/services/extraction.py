"""LLM extraction service — wires Instructor + Azure OpenAI to the SchedulingEvent schema.

Uses Instructor to enforce structured output from the LLM response.
Connector pattern reused from geoedge_municipios/backend/common/llm_provider.py.
"""

import os

import instructor
from dotenv import load_dotenv
from langfuse import Langfuse
from openai import AzureOpenAI

from backend.app.schemas.conversation import ConversationWindow
from backend.app.schemas.extraction import SchedulingEvent
from backend.app.services.prompt import build_extraction_prompt

load_dotenv()


def _get_azure_client() -> AzureOpenAI:
    """Create an Azure OpenAI client from .env credentials.

    Pattern reused from geoedge_municipios/backend/common/llm_provider.py.
    """
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

    if not api_key or not endpoint:
        raise ValueError(
            "Azure OpenAI credentials not found. "
            "Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT in .env."
        )

    return AzureOpenAI(
        api_key=api_key.strip('"'),
        api_version=api_version,
        azure_endpoint=endpoint,
    )


def _get_model_name() -> str:
    """Read the Azure OpenAI model/deployment name from .env."""
    return os.getenv("AZURE_OPENAI_MODEL", "geobot4")


def get_langfuse_client() -> Langfuse | None:
    """Initialize Langfuse client if credentials are available."""
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

    if public_key and secret_key:
        return Langfuse(public_key=public_key, secret_key=secret_key, host=host)
    return None


def extract_scheduling_event(
    conversation_window: ConversationWindow,
    *,
    model: str | None = None,
    prompt_version: str = "v0.1",
) -> SchedulingEvent:
    """Extract a structured scheduling event from a conversation window.

    Uses Instructor to enforce the SchedulingEvent Pydantic schema on the LLM output.
    Traces the call via Langfuse when credentials are available.

    Args:
        conversation_window: normalized conversation context.
        model: Azure OpenAI deployment name (defaults to AZURE_OPENAI_MODEL env var).
        prompt_version: version tag for tracing and regression tracking.

    Returns:
        SchedulingEvent with the extracted scheduling action.
    """
    if model is None:
        model = _get_model_name()

    langfuse = get_langfuse_client()

    # Build prompts
    system_prompt, user_prompt = build_extraction_prompt(conversation_window)

    # Create Instructor-wrapped Azure OpenAI client
    # Mode.JSON uses response_format=json_object plus Pydantic schema in the prompt
    azure_client = _get_azure_client()
    client = instructor.from_openai(
        azure_client,
        mode=instructor.Mode.JSON,
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
        event = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            temperature=0.1,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
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
    model: str | None = None,
) -> dict:
    """Extract and return as raw dict (useful for CLI/debugging)."""
    event = extract_scheduling_event(conversation_window, model=model)
    return event.model_dump()
