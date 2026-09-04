"""Contract shared by every webhook task-queue implementation."""

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class EnqueueResult:
    """Outcome of accepting a verified webhook for asynchronous processing."""

    accepted: bool
    duplicate: bool = False


class WebhookTaskQueue(Protocol):
    """Accepts a verified webhook body and guarantees durable handoff."""

    def enqueue(
        self, db: Session, provider_key: str, raw_body: bytes
    ) -> EnqueueResult:
        """Durably record the delivery for later processing.

        Must be idempotent on a byte-identical ``raw_body`` for the same
        ``provider_key`` (return ``duplicate=True``). Must only return
        ``accepted=True`` once the delivery is safely persisted/enqueued.
        """
        ...
