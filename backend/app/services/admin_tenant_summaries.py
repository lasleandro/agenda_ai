"""Bounded platform-admin tenant summary projection."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    AssistantSettings,
    Contact,
    Professional,
    ScheduledTask,
    ScheduledTaskRun,
    TenantFeature,
)
from app.schemas.api import TenantScheduledTaskSummary, TenantSummary
from app.services import assistant_settings as assistant_settings_service
from app.services import scheduled_tasks as scheduled_tasks_service
from app.services.tenant_features import COMMERCIAL_FINANCIALS


def _tenant_task_summary(
    task: ScheduledTask | None,
    professional: Professional,
    latest_run: ScheduledTaskRun | None,
    now: datetime,
) -> TenantScheduledTaskSummary:
    if task is None:
        return TenantScheduledTaskSummary(
            configured=False,
            enabled=False,
            local_time=None,
            consent_confirmed=False,
            readiness_issues=scheduled_tasks_service.task_readiness(professional),
            next_run_at=None,
            latest_run_status=None,
            latest_run_at=None,
        )
    return TenantScheduledTaskSummary(
        configured=True,
        enabled=task.enabled,
        local_time=task.local_time,
        consent_confirmed=task.consent_confirmed_at is not None,
        readiness_issues=scheduled_tasks_service.task_readiness(professional),
        next_run_at=scheduled_tasks_service.next_run_at(task, professional, now),
        latest_run_status=latest_run.status if latest_run is not None else None,
        latest_run_at=latest_run.created_at if latest_run is not None else None,
    )


def build_tenant_summaries(
    db: Session, professionals: list[Professional]
) -> list[TenantSummary]:
    """Build tile data only for the supplied bounded tenant collection."""
    professional_ids = [professional.id for professional in professionals]
    if not professional_ids:
        return []
    contact_counts = dict(
        db.query(Contact.professional_id, func.count(Contact.id))
        .filter(Contact.professional_id.in_(professional_ids))
        .group_by(Contact.professional_id)
        .all()
    )
    appointment_counts = dict(
        db.query(Appointment.professional_id, func.count(Appointment.id))
        .filter(Appointment.professional_id.in_(professional_ids))
        .group_by(Appointment.professional_id)
        .all()
    )
    commercial_financial_tenants = {
        professional_id
        for (professional_id,) in (
            db.query(TenantFeature.professional_id)
            .filter(
                TenantFeature.professional_id.in_(professional_ids),
                TenantFeature.feature_key == COMMERCIAL_FINANCIALS,
                TenantFeature.enabled.is_(True),
            )
            .all()
        )
    }
    assistant_settings_by_tenant = {
        row.professional_id: row
        for row in db.query(AssistantSettings)
        .filter(AssistantSettings.professional_id.in_(professional_ids))
        .all()
    }
    tasks_by_professional = {
        task.professional_id: task
        for task in db.query(ScheduledTask)
        .filter(
            ScheduledTask.professional_id.in_(professional_ids),
            ScheduledTask.task_type == "daily_agenda_summary",
        )
        .all()
    }
    task_ids = [task.id for task in tasks_by_professional.values()]
    latest_runs: dict[uuid.UUID, ScheduledTaskRun] = {}
    if task_ids:
        for run in (
            db.query(ScheduledTaskRun)
            .filter(ScheduledTaskRun.scheduled_task_id.in_(task_ids))
            .order_by(ScheduledTaskRun.created_at.desc())
            .all()
        ):
            latest_runs.setdefault(run.scheduled_task_id, run)
    now = datetime.now(timezone.utc)
    return [
        TenantSummary(
            id=professional.id,
            name=professional.name,
            status=professional.status,
            assistant_phone=professional.assistant_phone,
            contact_count=contact_counts.get(professional.id, 0),
            appointment_count=appointment_counts.get(professional.id, 0),
            commercial_financials_enabled=(
                professional.id in commercial_financial_tenants
            ),
            assistant_temperature=(
                assistant_settings_by_tenant[professional.id].temperature
                if professional.id in assistant_settings_by_tenant
                else assistant_settings_service.DEFAULT_TEMPERATURE
            ),
            assistant_memory_window_messages=(
                assistant_settings_by_tenant[professional.id].memory_window_messages
                if professional.id in assistant_settings_by_tenant
                else assistant_settings_service.DEFAULT_MEMORY_WINDOW_MESSAGES
            ),
            status_changed_at=professional.status_changed_at,
            status_reason=professional.status_reason,
            scheduled_task=_tenant_task_summary(
                tasks_by_professional.get(professional.id),
                professional,
                latest_runs.get(tasks_by_professional[professional.id].id)
                if professional.id in tasks_by_professional
                else None,
                now,
            ),
        )
        for professional in professionals
    ]

