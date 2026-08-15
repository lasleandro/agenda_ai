"""AgentChannelMessage model (AI Agent Operations Roadmap v0.1, Phase 3).

A lightweight per-professional conversation log for the WhatsApp AI agent
number, distinct from the customer-facing `Message`/`Conversation` pair
used by the passive observer — the interaction shape here is a direct
synchronous back-and-forth with the agent, not buffered batch extraction
over a human-to-human conversation. Rows are (role, content) pairs replayed
as `run_agent_turn`'s `messages` argument, windowed the same way the web
chat windows conversation history (`AssistantSettings.memory_window_messages`).
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentChannelMessage(Base):
    __tablename__ = "agent_channel_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_agent_channel_messages_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
