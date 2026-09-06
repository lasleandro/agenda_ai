"""Agent-channel binding handshake (Shared Platform AI Agent Number Roadmap
v0.1, Phase F).

The instructor opts the shared agent channel in by sending a short code —
shown in the authenticated web session — to the platform number from their own
WhatsApp. That proves live control of the number and produces an audited
opt-in. Normal agent-channel handling is gated on a confirmed binding
(``Professional.agent_binding_confirmed_at``).
"""

import hashlib
import os
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.integrations.whatsapp.platform_number import platform_agent_number
from app.models import AgentBindingChallenge, Professional
from app.services.operational_events import record_event

CODE_TTL_MINUTES = int(os.getenv("AGENT_BINDING_CODE_TTL_MINUTES", "15"))

_CODE_PREFIX = "ATIVAR-"
_CODE_RE = re.compile(r"ATIVAR-?([0-9]{6})", re.IGNORECASE)


class AgentBindingUnavailableError(RuntimeError):
    """The shared platform agent number is not configured."""


@dataclass(frozen=True)
class IssuedChallenge:
    code: str
    platform_number: str
    expires_at: datetime


@dataclass(frozen=True)
class BindingState:
    bound: bool
    confirmed_at: datetime | None
    platform_number: str | None


def _digest(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()


def _generate_code() -> str:
    return f"{_CODE_PREFIX}{secrets.randbelow(1_000_000):06d}"


def binding_state(db: Session, professional_id: uuid.UUID) -> BindingState:
    professional = db.get(Professional, professional_id)
    confirmed_at = (
        professional.agent_binding_confirmed_at if professional is not None else None
    )
    return BindingState(
        bound=confirmed_at is not None,
        confirmed_at=confirmed_at,
        platform_number=platform_agent_number(),
    )


def issue_challenge(db: Session, professional_id: uuid.UUID) -> IssuedChallenge:
    """Rotate the tenant's pending binding code and return the new one.

    Digest-only storage means a prior code cannot be re-shown; each call
    invalidates any earlier unconsumed challenge and mints a fresh code.
    """
    platform_number = platform_agent_number()
    if platform_number is None:
        raise AgentBindingUnavailableError

    now = datetime.now(timezone.utc)
    db.query(AgentBindingChallenge).filter(
        AgentBindingChallenge.professional_id == professional_id,
        AgentBindingChallenge.consumed_at.is_(None),
    ).delete(synchronize_session=False)

    code = _generate_code()
    expires_at = now + timedelta(minutes=CODE_TTL_MINUTES)
    db.add(
        AgentBindingChallenge(
            professional_id=professional_id,
            code_digest=_digest(code),
            expires_at=expires_at,
        )
    )
    db.commit()
    return IssuedChallenge(
        code=code, platform_number=platform_number, expires_at=expires_at
    )


def confirm_from_message(
    db: Session, professional: Professional, actor_user_id: uuid.UUID, text: str
) -> bool:
    """If ``text`` carries this tenant's live binding code, confirm the
    binding and return True. Otherwise return False and change nothing.
    """
    match = _CODE_RE.search(text or "")
    if match is None:
        return False
    code = f"{_CODE_PREFIX}{match.group(1)}"

    now = datetime.now(timezone.utc)
    challenge = (
        db.query(AgentBindingChallenge)
        .filter(
            AgentBindingChallenge.professional_id == professional.id,
            AgentBindingChallenge.code_digest == _digest(code),
            AgentBindingChallenge.consumed_at.is_(None),
            AgentBindingChallenge.expires_at > now,
        )
        .first()
    )
    if challenge is None:
        return False

    challenge.consumed_at = now
    professional.agent_binding_confirmed_at = now
    professional.agent_binding_confirmed_by = actor_user_id
    record_event(
        db,
        professional_id=professional.id,
        event_type="agent.binding.confirmed",
        occurred_at=now,
        actor_type="user",
        actor_id=actor_user_id,
        source_channel="whatsapp",
        entity_type="professional",
        entity_id=professional.id,
        correlation_id=uuid.uuid4(),
        payload={},
    )
    db.commit()
    return True


def revoke(
    db: Session,
    professional_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID,
    actor_type: str,
    source_channel: str,
) -> bool:
    """Clear the binding and drop any pending challenge. Returns whether a
    binding was actually cleared (idempotent otherwise)."""
    professional = db.get(Professional, professional_id)
    if professional is None or professional.agent_binding_confirmed_at is None:
        return False

    now = datetime.now(timezone.utc)
    professional.agent_binding_confirmed_at = None
    professional.agent_binding_confirmed_by = None
    db.query(AgentBindingChallenge).filter(
        AgentBindingChallenge.professional_id == professional_id,
        AgentBindingChallenge.consumed_at.is_(None),
    ).delete(synchronize_session=False)
    record_event(
        db,
        professional_id=professional_id,
        event_type="agent.binding.revoked",
        occurred_at=now,
        actor_type=actor_type,
        actor_id=actor_user_id,
        source_channel=source_channel,
        entity_type="professional",
        entity_id=professional_id,
        correlation_id=uuid.uuid4(),
        payload={},
    )
    db.commit()
    return True
