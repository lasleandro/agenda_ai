"""Select the webhook task-queue implementation from the environment."""

import os

from app.integrations.tasks.base import WebhookTaskQueue


def get_webhook_task_queue() -> WebhookTaskQueue:
    choice = os.getenv("WEBHOOK_TASK_QUEUE", "local").strip().lower()
    if choice in ("", "local", "receipt"):
        from app.integrations.tasks.local import LocalReceiptQueue

        return LocalReceiptQueue()
    raise RuntimeError(f"Unknown WEBHOOK_TASK_QUEUE: {choice!r}")
