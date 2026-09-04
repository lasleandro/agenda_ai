"""Deterministic idempotency key for a verified webhook delivery."""

import hashlib


def event_key(provider_key: str, raw_body: bytes) -> str:
    """Stable across provider retries: the same body yields the same key.

    Providers re-send the exact bytes on retry, so a digest of the verified
    body is a sufficient dedup key without parsing the envelope at ingress.
    """
    digest = hashlib.sha256(raw_body).hexdigest()
    return f"{provider_key}:sha256:{digest}"
