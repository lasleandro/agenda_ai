"""Process one durable webhook receipt.

Shared by the polling worker and by local inline processing. The signature
was already verified before the receipt was written, so this step only
parses and dispatches. Terminal outcomes set the receipt state here;
transient errors propagate so the caller can apply retry policy.
"""

import logging

from sqlalchemy.orm import Session

from app.chat.ingestion import ingest_provider_webhook
from app.integrations.whatsapp.contracts import WhatsAppPermanentError
from app.integrations.whatsapp.registry import get_whatsapp_provider
from app.models import WebhookReceipt

logger = logging.getLogger(__name__)


def process_receipt(db: Session, receipt: WebhookReceipt) -> None:
    """Run ingestion for a receipt and record its terminal state.

    Idempotent: a receipt already ``done`` returns immediately, and the
    downstream message/debounce writes and agent-channel handling are
    themselves idempotent, so a duplicate call cannot double-apply.
    """
    if receipt.status == "done":
        return

    provider = get_whatsapp_provider(receipt.provider_key)
    try:
        ingest_provider_webhook(db, bytes(receipt.raw_body), provider)
    except WhatsAppPermanentError as exc:
        db.rollback()
        receipt.status = "dead"
        receipt.last_error = f"permanent: {exc}"[:2000]
        db.commit()
        logger.warning(
            "webhook receipt %s is a permanent input error: %s", receipt.id, exc
        )
        return

    receipt.status = "done"
    receipt.last_error = None
    db.commit()
