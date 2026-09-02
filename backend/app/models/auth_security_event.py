"""Privacy-preserving audit and rate-limit events for authentication."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuthSecurityEvent(Base):
    """Stores hashed public identifiers and event categories, never credentials."""

    __tablename__ = "auth_security_events"
    __table_args__ = (
        Index("ix_auth_security_events_event_email_created", "event_type", "email_digest", "created_at"),
        Index("ix_auth_security_events_event_ip_created", "event_type", "ip_digest", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    email_digest: Mapped[str | None] = mapped_column(String(64))
    ip_digest: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
