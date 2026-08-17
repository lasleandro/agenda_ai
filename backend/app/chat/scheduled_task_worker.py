"""Poll and deliver tenant-scoped scheduled WhatsApp tasks."""

import logging
import os
import time

from app.database import SessionLocal
from app.integrations.whatsapp.registry import get_whatsapp_provider
from app.services.scheduled_tasks import process_due_scheduled_tasks

logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = int(os.getenv("SCHEDULED_TASK_POLL_SECONDS", "30"))


def run() -> None:
    """Run durable due-task processing until the process is stopped."""
    logger.info("scheduled task worker started, polling every %ss", POLL_INTERVAL_SECONDS)
    provider = get_whatsapp_provider()
    while True:
        db = SessionLocal()
        try:
            process_due_scheduled_tasks(db, provider)
        except Exception:
            db.rollback()
            logger.exception("scheduled task worker iteration failed")
        finally:
            db.close()
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run()
