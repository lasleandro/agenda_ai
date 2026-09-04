"""Durable receipt ledger for verified inbound provider webhooks.

The webhook endpoint verifies the signature, records one receipt per
delivery, and returns immediately. A background worker (or, in local
development, inline processing) drains receipts and runs the actual
ingestion/agent work. This keeps provider acknowledgement independent of
database, LLM, and outbound-provider latency, and makes retries safe: a
byte-identical redelivery collides on ``event_key`` and never reruns.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, LargeBinary, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

WEBHOOK_RECEIPT_STATUSES = ("received", "processing", "done", "failed", "dead")


class WebhookReceipt(Base):
    """One verified provider delivery, awaiting or past asynchronous handling."""

    __tablename__ = "webhook_receipts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('received', 'processing', 'done', 'failed', 'dead')",
            name="ck_webhook_receipts_status",
        ),
        Index("ix_webhook_receipts_status_claimed_at", "status", "claimed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider_key: Mapped[str] = mapped_column(String(50), nullable=False)
    # Deterministic idempotency key. Currently provider_key + digest of the
    # exact verified body, which is stable across provider retries.
    event_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    raw_body: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="received")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
