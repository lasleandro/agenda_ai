"""
Appointment candidate worker (Phase 2 — brief Section 12.2).

Polls pending_processing for conversations whose debounce window has closed,
runs the extraction pipeline, and persists an AppointmentCandidate.

Claim lease (deployment readiness): a conversation is *claimed*
(`claimed_at = now`, `attempts += 1`) before extraction and its row is
deleted only after extraction succeeds. A worker that dies mid-extraction
leaves a claimed row that becomes reclaimable once the lease expires, so no
work is silently lost. A conversation that keeps failing is dropped after
MAX_ATTEMPTS with an error log rather than spinning forever.

Usage:
    cd backend && python -m app.chat.candidate_worker
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from app.database import SessionLocal
from app.models import Conversation, PendingProcessing
from app.chat.pipeline import process_conversation

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = int(os.getenv("CANDIDATE_POLL_SECONDS", "5"))
# How long a claim is trusted before another worker may reclaim it.
CLAIM_LEASE_SECONDS = int(os.getenv("CANDIDATE_CLAIM_LEASE_SECONDS", "300"))
# Give up on a conversation after this many failed extraction attempts.
MAX_ATTEMPTS = int(os.getenv("CANDIDATE_MAX_ATTEMPTS", "5"))
# Rows claimed per poll iteration.
BATCH_SIZE = int(os.getenv("CANDIDATE_BATCH_SIZE", "10"))


def _delete_pending(db, conversation_id) -> None:
    db.query(PendingProcessing).filter(
        PendingProcessing.conversation_id == conversation_id
    ).delete(synchronize_session=False)
    db.commit()


def _claim_due_rows(db, now: datetime) -> list[PendingProcessing]:
    """Lock and claim up to BATCH_SIZE due, unclaimed-or-stale rows."""
    lease_cutoff = now - timedelta(seconds=CLAIM_LEASE_SECONDS)
    rows = (
        db.query(PendingProcessing)
        .filter(
            PendingProcessing.process_after <= now,
            or_(
                PendingProcessing.claimed_at.is_(None),
                PendingProcessing.claimed_at < lease_cutoff,
            ),
        )
        .order_by(PendingProcessing.process_after)
        .limit(BATCH_SIZE)
        .with_for_update(skip_locked=True)
        .all()
    )
    for row in rows:
        row.claimed_at = now
        row.attempts += 1
    db.commit()
    return rows


def process_due_conversations() -> int:
    """Claim and process every conversation whose debounce window has closed.

    Returns the number of candidates extracted.
    """
    db = SessionLocal()
    processed = 0
    try:
        now = datetime.now(timezone.utc)
        claimed = _claim_due_rows(db, now)

        for pending in claimed:
            conversation_id = pending.conversation_id
            attempts = pending.attempts

            conversation = (
                db.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
            )
            if conversation is None:
                _delete_pending(db, conversation_id)
                continue

            try:
                candidates = process_conversation(db, conversation)
                _delete_pending(db, conversation_id)
                logger.info(
                    "conversation=%s extracted_candidates=%s",
                    conversation_id, len(candidates),
                )
                processed += len(candidates)
            except Exception:
                db.rollback()
                if attempts >= MAX_ATTEMPTS:
                    # Drop the poison row so the queue drains; the claim lease
                    # would otherwise retry it indefinitely.
                    _delete_pending(db, conversation_id)
                    logger.error(
                        "extraction gave up for conversation=%s after %s attempts",
                        conversation_id, attempts,
                    )
                else:
                    logger.exception(
                        "extraction failed for conversation=%s (attempt %s/%s); "
                        "will retry after lease expires",
                        conversation_id, attempts, MAX_ATTEMPTS,
                    )
    finally:
        db.close()
    return processed


def run_forever():
    logger.info("candidate worker started, polling every %ss", POLL_INTERVAL_SECONDS)
    while True:
        try:
            process_due_conversations()
        except Exception:  # next poll safely retries; see passive_escalation_worker
            logger.exception("candidate worker iteration failed")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()
