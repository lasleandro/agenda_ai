"""
PendingProcessing model (brief Section 12.2 — conversation buffering/debounce).

One row per conversation awaiting extraction. A new message bumps
process_after forward (debounce reset) instead of inserting a duplicate row.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PendingProcessing(Base):
    __tablename__ = "pending_processing"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), unique=True, nullable=False
    )
    process_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Recoverable lease. The candidate worker sets claimed_at when it starts
    # extraction and deletes the row only on success. A claim older than the
    # lease is reclaimable, so a worker that dies mid-extraction does not lose
    # the work. attempts bounds retries of a poison conversation.
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conversation: Mapped["Conversation"] = relationship("Conversation")
