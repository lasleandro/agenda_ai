"""Poll durable authentication email deliveries."""

import logging
import os
import time

from app.database import SessionLocal
from app.services.auth_emails import process_due_email_deliveries

logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = int(os.getenv("EMAIL_DELIVERY_POLL_SECONDS", "15"))


def run() -> None:
    """Process due auth email jobs until stopped."""
    logger.info("email delivery worker started, polling every %ss", POLL_INTERVAL_SECONDS)
    while True:
        db = SessionLocal()
        try:
            process_due_email_deliveries(db)
        except Exception:
            db.rollback()
            logger.exception("email delivery worker iteration failed")
        finally:
            db.close()
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run()
