"""
Contact model (Section 10.2).

Represents a student / customer.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Plain string, not a DB enum, so new levels can be added later without a
# migration (customer ontology roadmap "modular" decision, 2026-08-05).
CONTACT_LEVELS = ("beginner", "intermediate", "advanced")


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        CheckConstraint(
            "commercial_status IS NULL OR commercial_status IN ('active', 'waiting', 'paused')",
            name="ck_contacts_commercial_status",
        ),
        CheckConstraint(
            "hourly_rate_cents IS NULL OR hourly_rate_cents BETWEEN 0 AND 100000000",
            name="ck_contacts_hourly_rate_cents",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False
    )
    provider_contact_id: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[str | None] = mapped_column(String(50))
    commercial_status: Mapped[str | None] = mapped_column(String(20))
    hourly_rate_cents: Mapped[int | None] = mapped_column(Integer)
    address_line: Mapped[str | None] = mapped_column(String(500))
    city: Mapped[str | None] = mapped_column(String(255))
    state: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str | None] = mapped_column(String(100))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    home_place_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("places.id"), nullable=True
    )
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    professional: Mapped["Professional"] = relationship("Professional")
    home_place: Mapped["Place"] = relationship("Place")
