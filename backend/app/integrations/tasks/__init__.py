"""Webhook task-queue abstraction.

``get_webhook_task_queue()`` returns the queue implementation selected by
the ``WEBHOOK_TASK_QUEUE`` environment variable. The webhook endpoint calls
``enqueue()`` and returns immediately; how the work is later executed is the
queue's concern.
"""

from app.integrations.tasks.base import EnqueueResult, WebhookTaskQueue
from app.integrations.tasks.registry import get_webhook_task_queue

__all__ = ["EnqueueResult", "WebhookTaskQueue", "get_webhook_task_queue"]
