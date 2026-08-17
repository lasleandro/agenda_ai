"""Tenant-isolated configuration, execution, and reconciliation for scheduled tasks."""

import os
import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.integrations.whatsapp.contracts import (
    WhatsAppDeliveryUnknownError,
    WhatsAppDeliveryUpdated,
    WhatsAppPermanentError,
    WhatsAppRetryableError,
    WhatsAppTemplateRequest,
)
from app.integrations.whatsapp.provider import WhatsAppProvider
from app.models import Professional, ScheduledTask, ScheduledTaskRun
from app.models.scheduled_task import DAILY_AGENDA_SUMMARY
from app.services import daily_agenda
from app.services.operational_events import record_event

MAX_LATENESS_MINUTES = int(os.getenv("SCHEDULED_TASK_MAX_LATENESS_MINUTES", "30"))
MAX_ATTEMPTS = int(os.getenv("SCHEDULED_TASK_MAX_ATTEMPTS", "3"))
RETRY_BASE_SECONDS = int(os.getenv("SCHEDULED_TASK_RETRY_BASE_SECONDS", "60"))


class ScheduledTaskConfigurationError(ValueError):
    """A safe, user-correctable scheduled-task configuration error."""


def task_readiness(professional: Professional) -> list[str]:
    """Return deterministic reasons this tenant cannot receive the task."""
    issues = []
    if professional.status != "active":
        issues.append("Tenant is inactive")
    if not professional.agent_phone:
        issues.append("Agent WhatsApp number is not configured")
    if not professional.assistant_phone:
        issues.append("Instructor WhatsApp number is not configured")
    try:
        daily_agenda.get_professional_timezone(professional)
    except ValueError:
        issues.append("Tenant timezone is invalid")
    return issues


def get_daily_agenda_task(
    db: Session, professional_id: uuid.UUID
) -> ScheduledTask | None:
    return (
        db.query(ScheduledTask)
        .filter(
            ScheduledTask.professional_id == professional_id,
            ScheduledTask.task_type == DAILY_AGENDA_SUMMARY,
        )
        .first()
    )


def update_daily_agenda_task(
    db: Session,
    *,
    professional_id: uuid.UUID,
    enabled: bool,
    local_time: time,
    consent_confirmed: bool,
    admin_user_id: uuid.UUID,
    source_ip: str | None,
    user_agent: str | None,
) -> ScheduledTask:
    """Persist one admin-managed daily agenda configuration and its audit event."""
    professional = db.get(Professional, professional_id)
    if professional is None:
        raise LookupError("Tenant not found")

    readiness = task_readiness(professional)
    if enabled and readiness:
        raise ScheduledTaskConfigurationError("; ".join(readiness))
    if enabled and not consent_confirmed:
        raise ScheduledTaskConfigurationError("Instructor consent must be confirmed")

    task = get_daily_agenda_task(db, professional_id)
    now = datetime.now(timezone.utc)
    before = _task_state(task) if task is not None else None
    if task is None:
        task = ScheduledTask(
            professional_id=professional_id,
            task_type=DAILY_AGENDA_SUMMARY,
            channel="whatsapp",
        )
        db.add(task)

    schedule_changed = task.enabled != enabled or task.local_time != local_time
    task.enabled = enabled
    task.local_time = local_time
    task.updated_by_user_id = admin_user_id
    if consent_confirmed:
        if task.consent_confirmed_at is None:
            task.consent_confirmed_at = now
            task.consent_confirmed_by_user_id = admin_user_id
    else:
        task.consent_confirmed_at = None
        task.consent_confirmed_by_user_id = None
    if enabled and schedule_changed:
        task.enabled_at = now
    elif not enabled:
        task.enabled_at = None

    db.flush()
    after = _task_state(task)
    record_event(
        db,
        professional_id=professional_id,
        event_type="scheduled_task.configuration.updated",
        occurred_at=now,
        actor_type="platform_admin",
        actor_id=admin_user_id,
        source_channel="web",
        entity_type="scheduled_task",
        entity_id=task.id,
        correlation_id=uuid.uuid4(),
        payload={
            "task_type": DAILY_AGENDA_SUMMARY,
            "source_ip": source_ip,
            "user_agent": user_agent,
        },
        before_state=before,
        after_state=after,
    )
    return task


def _task_state(task: ScheduledTask) -> dict:
    return {
        "enabled": task.enabled,
        "local_time": task.local_time.isoformat(timespec="minutes"),
        "consent_confirmed": task.consent_confirmed_at is not None,
    }


def next_run_at(task: ScheduledTask, professional: Professional, now_utc: datetime) -> datetime | None:
    """Calculate the next local scheduled instant without persisting derived state."""
    if not task.enabled or task_readiness(professional):
        return None
    timezone_value = daily_agenda.get_professional_timezone(professional)
    local_now = now_utc.astimezone(timezone_value)
    candidate = datetime.combine(local_now.date(), task.local_time, tzinfo=timezone_value)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def process_due_scheduled_tasks(
    db: Session, provider: WhatsAppProvider, now_utc: datetime | None = None
) -> int:
    """Claim due tenant tasks and retry durable runs; safe for repeated ticks."""
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    processed = 0
    tasks = (
        db.query(ScheduledTask, Professional)
        .join(Professional, ScheduledTask.professional_id == Professional.id)
        .filter(
            ScheduledTask.task_type == DAILY_AGENDA_SUMMARY,
            ScheduledTask.enabled.is_(True),
            Professional.status == "active",
        )
        .all()
    )
    for task, professional in tasks:
        run = _claim_due_run(db, task, professional, now)
        if run is None:
            continue
        if run.status == "skipped":
            processed += 1
            continue
        _deliver_run(db, run.id, provider, now)
        processed += 1

    retry_runs = (
        db.query(ScheduledTaskRun)
        .filter(
            ScheduledTaskRun.status == "retry_wait",
            ScheduledTaskRun.next_attempt_at <= now,
        )
        .with_for_update(skip_locked=True)
        .all()
    )
    for run in retry_runs:
        _deliver_run(db, run.id, provider, now)
        processed += 1
    return processed


def _claim_due_run(
    db: Session, task: ScheduledTask, professional: Professional, now_utc: datetime
) -> ScheduledTaskRun | None:
    readiness = task_readiness(professional)
    if readiness:
        return None
    timezone_value = daily_agenda.get_professional_timezone(professional)
    local_now = now_utc.astimezone(timezone_value)
    scheduled_for = datetime.combine(local_now.date(), task.local_time, tzinfo=timezone_value)
    if local_now < scheduled_for:
        return None
    if task.enabled_at is not None and task.enabled_at >= scheduled_for.astimezone(timezone.utc):
        return None

    status = "queued"
    if local_now - scheduled_for > timedelta(minutes=MAX_LATENESS_MINUTES):
        status = "skipped"
    statement = (
        insert(ScheduledTaskRun)
        .values(
            professional_id=professional.id,
            scheduled_task_id=task.id,
            target_local_date=local_now.date(),
            scheduled_for_at=scheduled_for.astimezone(timezone.utc),
            status=status,
            last_error_code="missed_delivery_window" if status == "skipped" else None,
            finished_at=now_utc if status == "skipped" else None,
        )
        .on_conflict_do_nothing(
            constraint="uq_scheduled_task_runs_task_date"
        )
        .returning(ScheduledTaskRun.id)
    )
    run_id = db.execute(statement).scalar_one_or_none()
    db.commit()
    return db.get(ScheduledTaskRun, run_id) if run_id is not None else None


def _deliver_run(
    db: Session, run_id: uuid.UUID, provider: WhatsAppProvider, now_utc: datetime
) -> None:
    run = db.get(ScheduledTaskRun, run_id)
    if run is None or run.status not in {"queued", "retry_wait"}:
        return
    task = db.get(ScheduledTask, run.scheduled_task_id)
    professional = db.get(Professional, run.professional_id)
    if task is None or professional is None or not task.enabled:
        run.status = "skipped"
        run.last_error_code = "task_disabled"
        run.finished_at = now_utc
        db.commit()
        return

    run.status = "processing"
    run.started_at = now_utc
    run.attempt_count += 1
    run.next_attempt_at = None
    db.commit()
    try:
        _, items = daily_agenda.list_daily_agenda_items(
            db, professional.id, run.target_local_date
        )
        body = daily_agenda.format_daily_agenda(run.target_local_date, items)
        run.agenda_item_count = len(items)
        run.class_count = sum(item.kind == "class" for item in items)
        run.event_count = sum(item.kind == "event" for item in items)
        run.rendered_body = body
        db.commit()

        result = provider.send_template(
            WhatsAppTemplateRequest(
                from_phone=professional.agent_phone or "",
                to_phone=professional.assistant_phone or "",
                template_key="daily_agenda",
                language=os.getenv("YCLOUD_DAILY_AGENDA_TEMPLATE_LANGUAGE", "pt_BR"),
                parameters=(
                    professional.name,
                    run.target_local_date.strftime("%d/%m"),
                    body,
                ),
                external_id=f"scheduled-task-run:{run.id}",
                ttl_seconds=_template_ttl_seconds(),
            )
        )
    except WhatsAppRetryableError as exc:
        _mark_retry_or_failed(db, run.id, now_utc, "provider_retryable", str(exc))
        return
    except WhatsAppDeliveryUnknownError as exc:
        run = db.get(ScheduledTaskRun, run_id)
        if run is not None:
            run.status = "delivery_unknown"
            run.last_error_code = "provider_delivery_unknown"
            run.last_error_detail = str(exc)[:500]
            run.finished_at = now_utc
            db.commit()
        return
    except (WhatsAppPermanentError, ValueError) as exc:
        run = db.get(ScheduledTaskRun, run_id)
        if run is not None:
            run.status = "failed"
            run.last_error_code = "provider_permanent" if isinstance(exc, WhatsAppPermanentError) else "agenda_configuration"
            run.last_error_detail = str(exc)[:500]
            run.finished_at = now_utc
            db.commit()
        return

    run = db.get(ScheduledTaskRun, run_id)
    if run is None:
        return
    run.status = "provider_accepted"
    run.provider_key = result.provider_key
    run.provider_message_id = result.provider_message_id
    run.provider_external_id = result.external_id
    run.accepted_at = result.accepted_at
    run.last_error_code = None
    run.last_error_detail = None
    db.commit()


def _mark_retry_or_failed(
    db: Session, run_id: uuid.UUID, now_utc: datetime, error_code: str, detail: str
) -> None:
    run = db.get(ScheduledTaskRun, run_id)
    if run is None:
        return
    run.last_error_code = error_code
    run.last_error_detail = detail[:500]
    if run.attempt_count >= MAX_ATTEMPTS:
        run.status = "failed"
        run.finished_at = now_utc
    else:
        run.status = "retry_wait"
        run.next_attempt_at = now_utc + timedelta(
            seconds=RETRY_BASE_SECONDS * (2 ** (run.attempt_count - 1))
        )
    db.commit()


def _template_ttl_seconds() -> int | None:
    value = os.getenv("YCLOUD_DAILY_AGENDA_TTL_SECONDS", "")
    return int(value) if value else None


def apply_delivery_update(db: Session, update: WhatsAppDeliveryUpdated) -> bool:
    """Apply one provider delivery event without allowing state regression."""
    run = (
        db.query(ScheduledTaskRun)
        .filter(
            ScheduledTaskRun.provider_key == update.provider_key,
            ScheduledTaskRun.provider_message_id == update.provider_message_id,
        )
        .first()
    )
    if run is None and update.external_id:
        run = (
            db.query(ScheduledTaskRun)
            .filter(
                ScheduledTaskRun.provider_key == update.provider_key,
                ScheduledTaskRun.provider_external_id == update.external_id,
            )
            .first()
        )
    if run is None:
        return False

    rank = {"provider_accepted": 1, "sent": 2, "delivered": 3, "read": 4}
    if update.status == "failed":
        if run.status not in {"delivered", "read"}:
            run.status = "failed"
            run.last_error_code = update.error_code or "provider_failed"
            run.last_error_detail = update.error_detail
            run.finished_at = update.occurred_at
            db.commit()
        return True
    if rank.get(update.status, 0) <= rank.get(run.status, 0):
        return True

    run.status = update.status
    if update.status == "sent":
        run.sent_at = update.occurred_at
    elif update.status == "delivered":
        run.delivered_at = update.occurred_at
    elif update.status == "read":
        run.read_at = update.occurred_at
        run.finished_at = update.occurred_at
    db.commit()
    return True
