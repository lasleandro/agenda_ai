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
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import require_platform_admin
from app.database import SessionLocal
from app.models import Appointment, AssistantSettings, Contact, Professional, TenantFeature
from app.schemas.api import (
    AssistantSettingsState,
    AssistantSettingsUpdate,
    TenantFeatureState,
    TenantFeatureUpdate,
    TenantListResponse,
    TenantSummary,
)
from app.services import assistant_settings as assistant_settings_service
from app.services.operational_events import record_event
from app.services.tenant_features import COMMERCIAL_FINANCIALS, set_tenant_feature

router = APIRouter(prefix="/api/admin", tags=["admin"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
        )
        for p in professionals
    ]
    return TenantListResponse(tenants=tenants)


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
