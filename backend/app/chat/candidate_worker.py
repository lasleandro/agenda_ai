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

            try:
                candidates = process_conversation(db, conversation)
                logger.info(
                    "conversation=%s extracted_candidates=%s",
                    conversation.id, len(candidates),
                )
                processed += len(candidates)
            except Exception:
                logger.exception("extraction failed for conversation=%s", conversation.id)
    finally:
        db.close()
    return processed


def run_forever():
    logger.info("candidate worker started, polling every %ss", POLL_INTERVAL_SECONDS)
    while True:
        process_due_conversations()
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()
