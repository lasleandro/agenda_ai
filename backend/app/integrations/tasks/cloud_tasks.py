"""Google Cloud Tasks webhook queue (deploy-time implementation).

Skeleton only. Selected with ``WEBHOOK_TASK_QUEUE=cloud_tasks``. Finishing
this at deployment requires:

  * adding ``google-cloud-tasks`` to requirements.txt;
  * ``CLOUD_TASKS_PROJECT``, ``CLOUD_TASKS_LOCATION``, ``CLOUD_TASKS_QUEUE``,
    ``CLOUD_TASKS_PROCESSOR_URL`` and an OIDC service-account audience in the
    environment;
  * the webhook-processor service exposing an authenticated endpoint that
    loads the receipt row and calls ``process_receipt``.

The receipt row is still written here first, so processing (local or Cloud
Run) always goes through the same ``webhook_receipts`` +
``process_receipt`` path and stays idempotent on ``event_key``.
"""

from sqlalchemy.orm import Session

from app.integrations.tasks.base import EnqueueResult


class CloudTasksQueue:
    def enqueue(
        self, db: Session, provider_key: str, raw_body: bytes
    ) -> EnqueueResult:
        raise NotImplementedError(
            "CloudTasksQueue is a deploy-time implementation; see the module "
            "docstring. Use WEBHOOK_TASK_QUEUE=local until it is wired up."
        )
