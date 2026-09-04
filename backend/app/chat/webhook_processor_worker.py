"""
Webhook processor worker (deployment readiness — durable webhook handoff).

Drains ``webhook_receipts``: the webhook endpoint verifies and records a
receipt, then returns; this worker runs the ingestion / agent-channel work
away from the provider request, with a recoverable claim lease and bounded
retries. In local development inline processing usually does this instead,
so running this worker is only required when
``WEBHOOK_INLINE_PROCESSING=false`` (the production default).

Usage:
    cd backend && python -m app.chat.webhook_processor_worker
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from app.database import SessionLocal
from app.models import WebhookReceipt
from app.chat.webhook_processor import process_receipt

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = int(os.getenv("WEBHOOK_PROCESSOR_POLL_SECONDS", "2"))
CLAIM_LEASE_SECONDS = int(os.getenv("WEBHOOK_PROCESSOR_CLAIM_LEASE_SECONDS", "120"))
MAX_ATTEMPTS = int(os.getenv("WEBHOOK_PROCESSOR_MAX_ATTEMPTS", "8"))
BATCH_SIZE = int(os.getenv("WEBHOOK_PROCESSOR_BATCH_SIZE", "20"))


def _claim_due_receipts(db, now: datetime) -> list[WebhookReceipt]:
    lease_cutoff = now - timedelta(seconds=CLAIM_LEASE_SECONDS)
    rows = (
        db.query(WebhookReceipt)
        .filter(
            WebhookReceipt.status.in_(("received", "failed", "processing")),
            or_(
                WebhookReceipt.claimed_at.is_(None),
                WebhookReceipt.claimed_at < lease_cutoff,
            ),
        )
        .order_by(WebhookReceipt.created_at)
        .limit(BATCH_SIZE)
        .with_for_update(skip_locked=True)
        .all()
    )
    for row in rows:
        row.status = "processing"
        row.claimed_at = now
        row.attempts += 1
    db.commit()
    return rows


def drain_once() -> int:
    """Claim and process one batch of due receipts. Returns count processed."""
    db = SessionLocal()
    processed = 0
    try:
        now = datetime.now(timezone.utc)
        for receipt in _claim_due_receipts(db, now):
            receipt_id = receipt.id
            attempts = receipt.attempts
            try:
                process_receipt(db, receipt)
                processed += 1
            except Exception as exc:  # transient — retry under the lease
                db.rollback()
                fresh = db.query(WebhookReceipt).filter(
                    WebhookReceipt.id == receipt_id
                ).one()
                if attempts >= MAX_ATTEMPTS:
                    fresh.status = "dead"
                    fresh.last_error = f"gave up after {attempts}: {exc}"[:2000]
                    logger.error(
                        "webhook receipt %s dead after %s attempts", receipt_id, attempts
                    )
                else:
                    fresh.status = "failed"
                    fresh.last_error = f"attempt {attempts}: {exc}"[:2000]
                    logger.exception(
                        "webhook receipt %s failed (attempt %s/%s); will retry",
                        receipt_id, attempts, MAX_ATTEMPTS,
                    )
                db.commit()
    finally:
        db.close()
    return processed


def run_forever():
    logger.info(
        "webhook processor worker started, polling every %ss", POLL_INTERVAL_SECONDS
    )
    while True:
        try:
            drain_once()
        except Exception:
            logger.exception("webhook processor iteration failed")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()
