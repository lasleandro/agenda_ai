"""Poll and deliver durable ambiguity-only passive escalations."""

import logging
import os
import time

from app.database import SessionLocal
from app.integrations.whatsapp.registry import get_whatsapp_provider
from app.services.passive_escalation import process_due_escalations

logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = int(os.getenv("PASSIVE_ESCALATION_POLL_SECONDS", "10"))


def run() -> None:
    logger.info("passive escalation worker started, polling every %ss", POLL_INTERVAL_SECONDS)
    provider = get_whatsapp_provider()
    while True:
        db = SessionLocal()
        try:
            process_due_escalations(db, provider)
        except Exception:  # next poll safely retries durable queued rows
            db.rollback()
            logger.exception("passive escalation worker iteration failed")
        finally:
            db.close()
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run()
