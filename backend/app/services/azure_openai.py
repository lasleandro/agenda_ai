"""Shared Azure OpenAI client factory.

Used by the customer-message extraction pipeline (`app/chat/extraction.py`)
and the instructor agent (`app/agent/orchestrator.py`). Connector pattern
reused from geoedge_municipios/backend/common/llm_provider.py.
"""

import os

from openai import AzureOpenAI


def get_azure_client() -> AzureOpenAI:
    """Create an Azure OpenAI client from .env credentials."""
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


def get_model_name() -> str:
    """Read the Azure OpenAI model/deployment name from .env."""
    return os.getenv("AZURE_OPENAI_MODEL", "geobot4")
