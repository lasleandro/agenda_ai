"""
Platform-admin tenant listing (multi-tenancy roadmap Phase D).

GET   /api/admin/tenants — one row per Professional (tenant), for the tile
                           grid a platform_admin lands on before impersonating.
PATCH /api/admin/tenants/{id}/features/commercial-financials
                         — audited optional-module control.
PUT   /api/admin/tenants/{id}/assistant-settings
                         — instructor-agent temperature/memory-window tuning.
"""

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.dependencies import require_platform_admin
from app.database import SessionLocal
from app.models import (
    Appointment,
    AssistantSettings,
    Contact,
    Professional,
    ScheduledTask,
    ScheduledTaskRun,
    TenantFeature,
)
from app.schemas.api import (
    AssistantSettingsState,
    AssistantSettingsUpdate,
    ScheduledTaskAdminListResponse,
    ScheduledTaskAdminSummary,
    ScheduledTaskHistoryResponse,
    ScheduledTaskRunLogEntry,
    ScheduledTaskRunLogResponse,
    ScheduledTaskRunState,
    ScheduledTaskTenantSuggestion,
    ScheduledTaskTenantSuggestionResponse,
    ScheduledTaskUpdate,
    TenantFeatureState,
    TenantFeatureUpdate,
    TenantListResponse,
    TenantScheduledTaskSummary,
    TenantSummary,
)
from app.services import assistant_settings as assistant_settings_service
from app.services import daily_agenda
from app.services.operational_events import record_event
from app.services import scheduled_tasks as scheduled_tasks_service
from app.services.tenant_features import COMMERCIAL_FINANCIALS, set_tenant_feature

router = APIRouter(prefix="/api/admin", tags=["admin"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    return f"***{phone[-4:]}" if len(phone) >= 4 else "***"


def _run_state(run: ScheduledTaskRun) -> ScheduledTaskRunState:
    return ScheduledTaskRunState.model_validate(run)


def _task_summary(
    task: ScheduledTask,
    professional: Professional,
    latest_run: ScheduledTaskRun | None,
    now: datetime,
) -> ScheduledTaskAdminSummary:
    return ScheduledTaskAdminSummary(
        professional_id=professional.id,
        professional_name=professional.name,
        tenant_status=professional.status,
        task_id=task.id,
        enabled=task.enabled,
        local_time=task.local_time,
        timezone=professional.timezone,
        consent_confirmed=task.consent_confirmed_at is not None,
        sender_phone_masked=_mask_phone(professional.agent_phone),
        recipient_phone_masked=_mask_phone(professional.assistant_phone),
        readiness_issues=scheduled_tasks_service.task_readiness(professional),
        next_run_at=scheduled_tasks_service.next_run_at(task, professional, now),
        latest_run=_run_state(latest_run) if latest_run is not None else None,
    )


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


@router.get("/tenants", response_model=TenantListResponse)
def list_tenants(
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_platform_admin),
):
    contact_counts = dict(
        db.query(Contact.professional_id, func.count(Contact.id))
        .group_by(Contact.professional_id)
        .all()
    )
    appointment_counts = dict(
        db.query(Appointment.professional_id, func.count(Appointment.id))
        .group_by(Appointment.professional_id)
        .all()
    )
    commercial_financial_tenants = {
        professional_id
        for (professional_id,) in (
            db.query(TenantFeature.professional_id)
            .filter(
                TenantFeature.feature_key == COMMERCIAL_FINANCIALS,
                TenantFeature.enabled.is_(True),
            )
            .all()
        )
    }

    assistant_settings_by_tenant = {
        row.professional_id: row for row in db.query(AssistantSettings).all()
    }

    professionals = db.query(Professional).order_by(Professional.name).all()
    tasks_by_professional = {
        task.professional_id: task
        for task in db.query(ScheduledTask)
        .filter(ScheduledTask.task_type == "daily_agenda_summary")
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
    tenants = [
        TenantSummary(
            id=p.id,
            name=p.name,
            status=p.status,
            assistant_phone=p.assistant_phone,
            contact_count=contact_counts.get(p.id, 0),
            appointment_count=appointment_counts.get(p.id, 0),
            commercial_financials_enabled=p.id in commercial_financial_tenants,
            assistant_temperature=(
                assistant_settings_by_tenant[p.id].temperature
                if p.id in assistant_settings_by_tenant
                else assistant_settings_service.DEFAULT_TEMPERATURE
            ),
            assistant_memory_window_messages=(
                assistant_settings_by_tenant[p.id].memory_window_messages
                if p.id in assistant_settings_by_tenant
                else assistant_settings_service.DEFAULT_MEMORY_WINDOW_MESSAGES
            ),
            scheduled_task=_tenant_task_summary(
                tasks_by_professional.get(p.id),
                p,
                latest_runs.get(tasks_by_professional[p.id].id)
                if p.id in tasks_by_professional
                else None,
                now,
            ),
        )
        for p in professionals
    ]
    return TenantListResponse(tenants=tenants)


@router.get("/scheduled-tasks", response_model=ScheduledTaskAdminListResponse)
def list_scheduled_tasks(
    q: str = Query(default="", max_length=100),
    task_type: str = Query(default="daily_agenda_summary"),
    enabled: bool | None = None,
    tenant_status: str | None = Query(default=None, max_length=50),
    readiness: str | None = Query(default=None, pattern="^(ready|blocked)$"),
    latest_run_status: str | None = Query(default=None, max_length=30),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_platform_admin),
):
    if task_type != "daily_agenda_summary":
        raise HTTPException(status_code=422, detail="Unsupported task type")
    now = datetime.now(timezone.utc)
    query = (
        db.query(ScheduledTask, Professional)
        .join(Professional, ScheduledTask.professional_id == Professional.id)
        .filter(ScheduledTask.task_type == task_type)
    )
    if q.strip():
        query = query.filter(Professional.name.ilike(f"%{q.strip()}%"))
    if enabled is not None:
        query = query.filter(ScheduledTask.enabled.is_(enabled))
    if tenant_status:
        query = query.filter(Professional.status == tenant_status)
    if readiness == "ready":
        query = query.filter(
            Professional.status == "active",
            Professional.agent_phone.is_not(None),
            Professional.assistant_phone.is_not(None),
        )
    elif readiness == "blocked":
        query = query.filter(
            or_(
                Professional.status != "active",
                Professional.agent_phone.is_(None),
                Professional.assistant_phone.is_(None),
            )
        )
    if latest_run_status:
        latest_status = (
            db.query(ScheduledTaskRun.status)
            .filter(ScheduledTaskRun.scheduled_task_id == ScheduledTask.id)
            .order_by(ScheduledTaskRun.created_at.desc())
            .limit(1)
            .correlate(ScheduledTask)
            .scalar_subquery()
        )
        query = query.filter(latest_status == latest_run_status)

    total = query.order_by(None).count()
    rows = (
        query.order_by(Professional.name, ScheduledTask.created_at)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    task_ids = [task.id for task, _professional in rows]
    latest_runs: dict[uuid.UUID, ScheduledTaskRun] = {}
    if task_ids:
        for run in (
            db.query(ScheduledTaskRun)
            .filter(ScheduledTaskRun.scheduled_task_id.in_(task_ids))
            .order_by(ScheduledTaskRun.created_at.desc())
            .all()
        ):
            latest_runs.setdefault(run.scheduled_task_id, run)
    return ScheduledTaskAdminListResponse(
        tasks=[
            _task_summary(task, professional, latest_runs.get(task.id), now)
            for task, professional in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/scheduled-task-tenants", response_model=ScheduledTaskTenantSuggestionResponse
)
def search_scheduled_task_tenants(
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_platform_admin),
):
    query = db.query(Professional).order_by(Professional.name)
    if q.strip():
        query = query.filter(Professional.name.ilike(f"%{q.strip()}%"))
    professionals = query.limit(limit).all()
    professional_ids = [professional.id for professional in professionals]
    configured_ids = {
        professional_id
        for (professional_id,) in (
            db.query(ScheduledTask.professional_id)
            .filter(
                ScheduledTask.professional_id.in_(professional_ids),
                ScheduledTask.task_type == "daily_agenda_summary",
            )
            .all()
        )
    } if professional_ids else set()
    return ScheduledTaskTenantSuggestionResponse(
        tenants=[
            ScheduledTaskTenantSuggestion(
                id=professional.id,
                name=professional.name,
                status=professional.status,
                timezone=professional.timezone,
                task_configured=professional.id in configured_ids,
                readiness_issues=scheduled_tasks_service.task_readiness(professional),
            )
            for professional in professionals
        ]
    )


@router.put(
    "/tenants/{professional_id}/scheduled-tasks/daily-agenda",
    response_model=ScheduledTaskAdminSummary,
)
def update_daily_agenda_task(
    professional_id: uuid.UUID,
    body: ScheduledTaskUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_platform_admin),
):
    try:
        task = scheduled_tasks_service.update_daily_agenda_task(
            db,
            professional_id=professional_id,
            enabled=body.enabled,
            local_time=body.local_time,
            consent_confirmed=body.consent_confirmed,
            admin_user_id=uuid.UUID(admin["user_id"]),
            source_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Tenant not found") from exc
    except scheduled_tasks_service.ScheduledTaskConfigurationError as exc:
        status_code = 409 if "configured" in str(exc) or "inactive" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    db.commit()
    professional = db.get(Professional, professional_id)
    assert professional is not None
    return ScheduledTaskAdminSummary(
        professional_id=professional.id,
        professional_name=professional.name,
        tenant_status=professional.status,
        task_id=task.id,
        enabled=task.enabled,
        local_time=task.local_time,
        timezone=professional.timezone,
        consent_confirmed=task.consent_confirmed_at is not None,
        sender_phone_masked=_mask_phone(professional.agent_phone),
        recipient_phone_masked=_mask_phone(professional.assistant_phone),
        readiness_issues=scheduled_tasks_service.task_readiness(professional),
        next_run_at=scheduled_tasks_service.next_run_at(
            task, professional, datetime.now(timezone.utc)
        ),
        latest_run=None,
    )


@router.get(
    "/tenants/{professional_id}/scheduled-tasks/daily-agenda/runs",
    response_model=ScheduledTaskHistoryResponse,
)
def list_daily_agenda_runs(
    professional_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_platform_admin),
):
    if db.get(Professional, professional_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    runs = (
        db.query(ScheduledTaskRun)
        .filter(ScheduledTaskRun.professional_id == professional_id)
        .order_by(ScheduledTaskRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return ScheduledTaskHistoryResponse(runs=[_run_state(run) for run in runs])


@router.get("/scheduled-task-runs", response_model=ScheduledTaskRunLogResponse)
def list_scheduled_task_runs(
    q: str = Query(default="", max_length=100),
    professional_id: uuid.UUID | None = None,
    task_type: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None, max_length=30),
    date_from: date | None = None,
    date_to: date | None = None,
    provider_key: str | None = Query(default=None, max_length=50),
    has_error: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_platform_admin),
):
    if task_type and task_type != "daily_agenda_summary":
        raise HTTPException(status_code=422, detail="Unsupported task type")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to")

    query = (
        db.query(ScheduledTaskRun, ScheduledTask, Professional)
        .join(ScheduledTask, ScheduledTaskRun.scheduled_task_id == ScheduledTask.id)
        .join(Professional, ScheduledTaskRun.professional_id == Professional.id)
    )
    if q.strip():
        query = query.filter(Professional.name.ilike(f"%{q.strip()}%"))
    if professional_id:
        query = query.filter(ScheduledTaskRun.professional_id == professional_id)
    if task_type:
        query = query.filter(ScheduledTask.task_type == task_type)
    if status:
        query = query.filter(ScheduledTaskRun.status == status)
    if date_from:
        query = query.filter(ScheduledTaskRun.target_local_date >= date_from)
    if date_to:
        query = query.filter(ScheduledTaskRun.target_local_date <= date_to)
    if provider_key:
        query = query.filter(ScheduledTaskRun.provider_key == provider_key)
    if has_error is True:
        query = query.filter(ScheduledTaskRun.last_error_code.is_not(None))
    elif has_error is False:
        query = query.filter(ScheduledTaskRun.last_error_code.is_(None))

    total = query.order_by(None).count()
    rows = (
        query.order_by(ScheduledTaskRun.created_at.desc(), ScheduledTaskRun.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    entries = []
    for run, task, professional in rows:
        try:
            local_time = run.scheduled_for_at.astimezone(
                daily_agenda.get_professional_timezone(professional)
            ).strftime("%H:%M")
        except ValueError:
            local_time = run.scheduled_for_at.astimezone(timezone.utc).strftime("%H:%M UTC")
        entries.append(
            ScheduledTaskRunLogEntry(
                id=run.id,
                professional_id=professional.id,
                professional_name=professional.name,
                task_type=task.task_type,
                target_local_date=run.target_local_date,
                scheduled_for_at=run.scheduled_for_at,
                scheduled_local_time=local_time,
                status=run.status,
                attempt_count=run.attempt_count,
                agenda_item_count=run.agenda_item_count,
                provider_key=run.provider_key,
                accepted_at=run.accepted_at,
                sent_at=run.sent_at,
                delivered_at=run.delivered_at,
                read_at=run.read_at,
                finished_at=run.finished_at,
                last_error_code=run.last_error_code,
                last_error_detail=run.last_error_detail,
                created_at=run.created_at,
            )
        )
    return ScheduledTaskRunLogResponse(
        runs=entries,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch(
    "/tenants/{professional_id}/features/commercial-financials",
    response_model=TenantFeatureState,
)
def update_commercial_financials(
    professional_id: uuid.UUID,
    body: TenantFeatureUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_platform_admin),
):
    professional_exists = (
        db.query(Professional.id).filter(Professional.id == professional_id).first()
    )
    if professional_exists is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    enabled = set_tenant_feature(
        db,
        professional_id=professional_id,
        feature_key=COMMERCIAL_FINANCIALS,
        enabled=body.enabled,
        admin_user_id=uuid.UUID(admin["user_id"]),
        source_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return TenantFeatureState(
        feature_key=COMMERCIAL_FINANCIALS,
        enabled=enabled,
    )


@router.put(
    "/tenants/{professional_id}/assistant-settings",
    response_model=AssistantSettingsState,
)
def update_assistant_settings(
    professional_id: uuid.UUID,
    body: AssistantSettingsUpdate,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_platform_admin),
):
    professional_exists = (
        db.query(Professional.id).filter(Professional.id == professional_id).first()
    )
    if professional_exists is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    previous = assistant_settings_service.get_assistant_settings(db, professional_id)
    try:
        updated = assistant_settings_service.update_assistant_settings(
            db,
            professional_id,
            temperature=body.temperature,
            memory_window_messages=body.memory_window_messages,
            updated_by_user_id=uuid.UUID(admin["user_id"]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    correlation_id = uuid.uuid4()
    record_event(
        db,
        professional_id=professional_id,
        event_type="assistant.settings.updated",
        occurred_at=datetime.now(timezone.utc),
        actor_type="platform_admin",
        actor_id=uuid.UUID(admin["user_id"]),
        source_channel="web",
        entity_type="assistant_settings",
        entity_id=professional_id,
        correlation_id=correlation_id,
        payload={
            "temperature": updated.temperature,
            "memory_window_messages": updated.memory_window_messages,
        },
        before_state={
            "temperature": previous.temperature,
            "memory_window_messages": previous.memory_window_messages,
        },
        after_state={
            "temperature": updated.temperature,
            "memory_window_messages": updated.memory_window_messages,
        },
    )
    db.commit()
    return AssistantSettingsState(
        temperature=updated.temperature,
        memory_window_messages=updated.memory_window_messages,
    )
