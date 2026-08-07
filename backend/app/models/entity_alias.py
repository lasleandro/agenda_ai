"""
EntityAlias model (operational ontology roadmap v0.2, Phase 0) — a
tenant-scoped alternate name for a contact, place, or recurring slot (the
unit of group identity, per "interpretation 1"), used for deterministic
natural-language entity resolution (e.g. an agent matching "Clube Harmonia"
to a Place).

Polymorphic by design: `entity_id` intentionally has no foreign key, since
it can reference any of several tables depending on `entity_type`. Callers
are responsible for verifying the referenced entity exists and belongs to
`professional_id` before creating an alias.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

ENTITY_ALIAS_TYPES = ("contact", "place", "recurring_slot")


class EntityAlias(Base):
    __tablename__ = "entity_aliases"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('contact', 'place', 'recurring_slot')",
            name="ck_entity_aliases_entity_type",
        ),
        UniqueConstraint(
            "professional_id",
            "entity_type",
            "normalized_alias",
            name="uq_entity_aliases_professional_type_normalized",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    professional: Mapped["Professional"] = relationship("Professional")
