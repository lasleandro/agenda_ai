"""
Appointment candidate worker (Phase 2 — brief Section 12.2).

Polls pending_processing for conversations whose debounce window has
closed, runs the extraction pipeline, and persists an AppointmentCandidate.
No external broker — a `FOR UPDATE SKIP LOCKED` poll loop is sufficient for
one instructor per the brief's PoC guidance.

Usage:
    cd backend && python -m app.chat.candidate_worker
"""

import logging
import time
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import Conversation, PendingProcessing
from app.chat.pipeline import process_conversation

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5


def process_due_conversations() -> int:
    """Process every conversation whose debounce window has closed.

    Returns the number processed.
    """
    db = SessionLocal()
    processed = 0
    try:
        due = (
            db.query(PendingProcessing)
            .filter(PendingProcessing.process_after <= datetime.now(timezone.utc))
            .with_for_update(skip_locked=True)
            .all()
        )
        for pending in due:
            conversation = db.query(Conversation).filter(Conversation.id == pending.conversation_id).first()
            db.delete(pending)
            db.commit()

            if conversation is None:
                continue

            # Captured before process_conversation runs: db.commit() above
            # expires every attribute on `conversation`, so referencing
            # conversation.id after a failed flush forces a lazy reload —
            # which raises PendingRollbackError on a session that still
            # needs db.rollback(), crashing this except block itself (and
            # with no try/except around run_forever()'s loop, the whole
            # worker process).
            conversation_id = conversation.id

            try:
                candidates = process_conversation(db, conversation)
                logger.info(
                    "conversation=%s extracted_candidates=%s",
                    conversation_id, len(candidates),
                )
                processed += len(candidates)
            except Exception:
                db.rollback()
                logger.exception("extraction failed for conversation=%s", conversation_id)
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
