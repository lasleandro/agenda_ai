"""
User model — dashboard login identity (multi-tenancy roadmap Phase B).

Two roles:
  - "platform_admin": no professional_id (global); lands on the tenant tile
    grid and must impersonate a Professional to view tenant data.
  - "professional": professional_id is required; scoped to that tenant only.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "(role = 'platform_admin' AND professional_id IS NULL) OR "
            "(role = 'professional' AND professional_id IS NOT NULL)",
            name="ck_users_role_professional_id",
        ),
        CheckConstraint(
            "status IN ('pending_activation', 'active', 'disabled')",
            name="ck_users_status",
        ),
        CheckConstraint(
            "status <> 'active' OR hashed_password IS NOT NULL",
            name="ck_users_active_requires_password",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    professional_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), default="active")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auth_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # professionals.status_changed_by adds a second users<->professionals FK
    # path, so the join column must be named explicitly.
    professional: Mapped["Professional"] = relationship(
        "Professional", foreign_keys=[professional_id]
    )
