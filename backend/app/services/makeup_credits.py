"""Make-up class credit eligibility and lifecycle.

Phase 1: notice-window eligibility check (pure function, no DB).
Phase 2: credit granting, balance queries.
Phases 3-5: redemption, expiry (see roadmap).
"""

import logging
import uuid
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models import (
    MakeupClassCredit,
    ProfessionalFinancialSettings,
    RecurringSlotParticipant,
)
from app.services.operational_events import record_event

logger = logging.getLogger(__name__)

MAX_OUTSTANDING_CREDITS = 10


def has_sufficient_cancellation_notice(
    occurrence_starts_at: datetime,
    cancelled_at: datetime,
    notice_hours: int,
) -> bool:
    """Return True if the cancellation was made *more* than `notice_hours`
    before the occurrence's scheduled start time.

    This is a pure function — no DB access, trivially unit-testable.
    """
    if notice_hours <= 0:
        return True
    delta = occurrence_starts_at - cancelled_at
    return delta.total_seconds() > (notice_hours * 3600)


def _is_recurring_participant(
    db: Session,
    contact_id: uuid.UUID,
    recurring_slot_id: uuid.UUID,
) -> bool:
    return (
        db.query(RecurringSlotParticipant.id)
        .filter(
            RecurringSlotParticipant.contact_id == contact_id,
            RecurringSlotParticipant.recurring_slot_id == recurring_slot_id,
        )
        .first()
        is not None
    )


def _existing_credit_for_event(
    db: Session,
    contact_id: uuid.UUID,
    origin_event_id: uuid.UUID,
) -> bool:
    return (
        db.query(MakeupClassCredit.id)
        .filter(
            MakeupClassCredit.contact_id == contact_id,
            MakeupClassCredit.origin_event_id == origin_event_id,
        )
        .first()
        is not None
    )


def _outstanding_count(
    db: Session,
    professional_id: uuid.UUID,
    contact_id: uuid.UUID,
) -> int:
    return (
        db.query(MakeupClassCredit)
        .filter(
            MakeupClassCredit.professional_id == professional_id,
            MakeupClassCredit.contact_id == contact_id,
            MakeupClassCredit.status == "available",
        )
        .count()
    )


def get_available_credits_count(
    db: Session,
    professional_id: uuid.UUID,
    contact_id: uuid.UUID,
) -> int:
    """Return the number of available (unredeemed, unexpired) credits."""
    return _outstanding_count(db, professional_id, contact_id)


def list_available_credits(
    db: Session,
    professional_id: uuid.UUID,
    contact_id: uuid.UUID,
) -> list[MakeupClassCredit]:
    """Return the individual available credit records (with their IDs) for
    one contact — the only way to discover a credit_id for
    propose_redeem_makeup_credit; get_available_credits_count only exposes
    a count."""
    return (
        db.query(MakeupClassCredit)
        .filter(
            MakeupClassCredit.professional_id == professional_id,
            MakeupClassCredit.contact_id == contact_id,
            MakeupClassCredit.status == "available",
        )
        .order_by(MakeupClassCredit.granted_at)
        .all()
    )


def grant_credit_if_eligible(
    db: Session,
    *,
    professional_id: uuid.UUID,
    contact_id: uuid.UUID,
    recurring_slot_id: uuid.UUID,
    origin_event_id: uuid.UUID,
    occurrence_date: date,
    occurrence_starts_at: datetime,
    cancelled_at: datetime,
    correlation_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    source_channel: str = "web",
) -> MakeupClassCredit | None:
    """Grant a make-up credit to one contact if they qualify.

    Conditions (checked in order, cheap synchronous checks):
    1. Contact is a recurring participant of the cancelled slot.
    2. Cancellation happened more than `cancellation_notice_hours` before
       the occurrence start (per tenant settings).
    3. No duplicate credit for the same (contact_id, origin_event_id) pair.
    4. Contact hasn't hit the MAX_OUTSTANDING_CREDITS cap.

    Returns the new MakeupClassCredit or None if ineligible.
    """

    if not _is_recurring_participant(db, contact_id, recurring_slot_id):
        logger.debug(
            "makeup_credit: contact %s is not a participant of slot %s — skipping",
            contact_id,
            recurring_slot_id,
        )
        return None

    settings = (
        db.query(ProfessionalFinancialSettings)
        .filter(ProfessionalFinancialSettings.professional_id == professional_id)
        .first()
    )
    notice_hours = settings.cancellation_notice_hours if settings else 24

    if not has_sufficient_cancellation_notice(
        occurrence_starts_at, cancelled_at, notice_hours
    ):
        logger.debug(
            "makeup_credit: insufficient notice for contact %s (needed %sh) — skipping",
            contact_id,
            notice_hours,
        )
        return None

    if _existing_credit_for_event(db, contact_id, origin_event_id):
        logger.debug(
            "makeup_credit: contact %s already has a credit for event %s — skipping",
            contact_id,
            origin_event_id,
        )
        return None

    outstanding = _outstanding_count(db, professional_id, contact_id)
    if outstanding >= MAX_OUTSTANDING_CREDITS:
        logger.debug(
            "makeup_credit: contact %s already has %s outstanding credits — skipping",
            contact_id,
            outstanding,
        )
        return None

    credit = MakeupClassCredit(
        professional_id=professional_id,
        contact_id=contact_id,
        origin_event_id=origin_event_id,
        origin_recurring_slot_id=recurring_slot_id,
        origin_occurrence_date=occurrence_date,
        status="available",
    )
    db.add(credit)
    db.flush()

    record_event(
        db,
        professional_id=professional_id,
        event_type="makeup_credit.granted",
        occurred_at=datetime.now().astimezone(),
        actor_type="user",
        actor_id=actor_user_id,
        source_channel=source_channel,
        entity_type="makeup_class_credit",
        entity_id=credit.id,
        correlation_id=correlation_id,
        causation_id=origin_event_id,
        payload={
            "contact_id": str(contact_id),
            "recurring_slot_id": str(recurring_slot_id),
            "occurrence_date": occurrence_date.isoformat(),
        },
        before_state=None,
        after_state={"status": "available"},
    )

    return credit
