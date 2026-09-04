"""In-process webhook queue: a durable receipt row drained by a worker.

This is the default. It needs no external broker: the webhook endpoint
inserts a ``webhook_receipts`` row and returns; ``webhook_processor_worker``
polls and processes it. In local development (and any environment with
``WEBHOOK_INLINE_PROCESSING=true``) the receipt is also processed inline so
the manual test loop stays instant without running the worker.

A broker-backed queue (for example Azure Service Bus) can replace this behind
``WebhookTaskQueue`` with no change to the endpoint or the processing logic —
both call ``process_receipt``.
"""

import logging

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.settings import get_bool, is_production
from app.database import SessionLocal
from app.integrations.tasks.base import EnqueueResult
from app.integrations.tasks.keys import event_key
from app.models import WebhookReceipt

logger = logging.getLogger(__name__)


def _inline_processing_enabled() -> bool:
    """Process receipts synchronously when there is no worker to drain them."""
    return get_bool("WEBHOOK_INLINE_PROCESSING", not is_production())


class LocalReceiptQueue:
    def enqueue(
        self, db: Session, provider_key: str, raw_body: bytes
    ) -> EnqueueResult:
        key = event_key(provider_key, raw_body)
        stmt = (
            pg_insert(WebhookReceipt)
            .values(
                provider_key=provider_key,
                event_key=key,
                raw_body=raw_body,
                status="received",
            )
            .on_conflict_do_nothing(index_elements=["event_key"])
        )
        result = db.execute(stmt)
        db.commit()
        if result.rowcount == 0:
            # Byte-identical redelivery — already recorded.
            return EnqueueResult(accepted=True, duplicate=True)

        if _inline_processing_enabled():
            self._process_inline(key)
        return EnqueueResult(accepted=True, duplicate=False)

    @staticmethod
    def _process_inline(key: str) -> None:
        from app.chat.webhook_processor import process_receipt

        worker_db = SessionLocal()
        try:
            receipt = (
                worker_db.query(WebhookReceipt)
                .filter(WebhookReceipt.event_key == key)
                .one()
            )
            try:
                process_receipt(worker_db, receipt)
            except Exception:
                # Never fail the webhook ack on inline processing. Leave the
                # receipt visibly 'failed' so the webhook processor worker
                # (or a manual replay) can pick it up.
                worker_db.rollback()
                worker_db.query(WebhookReceipt).filter(
                    WebhookReceipt.event_key == key
                ).update({"status": "failed"}, synchronize_session=False)
                worker_db.commit()
                logger.exception("inline webhook processing failed for %s", key)
        finally:
            worker_db.close()
