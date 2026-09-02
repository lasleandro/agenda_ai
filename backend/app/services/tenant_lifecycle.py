"""Tenant lifecycle transitions (suspend / reactivate / archive / restore).

Reversible soft states only — nothing is physically deleted. Every transition
out of ``active`` force-logs-out the tenant's users by bumping their
``auth_version`` and appends one row to the operational-event ledger.

See docs/ROADMAPS/tenant_suspend_and_archive_roadmap_v0.1_2026-09-01.md.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Professional, User
from app.models.professional import (
    TENANT_STATUS_ACTIVE,
    TENANT_STATUS_ARCHIVED,
    TENANT_STATUS_SUSPENDED,
    TENANT_STATUSES,
)
from app.services.operational_events import record_event

_REASON_MAX_LENGTH = 500

_EVENT_TYPE_LEAVING_ACTIVE = {
    TENANT_STATUS_SUSPENDED: "tenant.suspended",
    TENANT_STATUS_ARCHIVED: "tenant.archived",
}


class TenantLifecycleError(Exception):
    """Raised for an unsupported tenant status transition request."""


def _return_to_active_event_type(previous_status: str) -> str:
    if previous_status == TENANT_STATUS_ARCHIVED:
        return "tenant.restored"
    return "tenant.reactivated"


def _clean_reason(reason: str | None) -> str | None:
    if not reason:
        return None
    trimmed = reason.strip()
    return trimmed[:_REASON_MAX_LENGTH] or None


def set_tenant_status(
    db: Session,
    *,
    professional_id: uuid.UUID,
    target_status: str,
    admin_user_id: uuid.UUID,
    reason: str | None = None,
    source_ip: str | None = None,
    user_agent: str | None = None,
) -> Professional:
    """Move a tenant to ``target_status``, audited. Caller commits.

    Returns the ``Professional`` unchanged when it is already in the target
    status (idempotent no-op — no audit row, no session bump).
    """
    if target_status not in TENANT_STATUSES:
        raise TenantLifecycleError(f"Unknown tenant status: {target_status}")

    professional = db.get(Professional, professional_id)
    if professional is None:
        raise LookupError("Tenant not found")

    previous_status = professional.status
    if previous_status == target_status:
        return professional

    now = datetime.now(timezone.utc)
    cleaned_reason = _clean_reason(reason)

    leaving_active = (
        previous_status == TENANT_STATUS_ACTIVE and target_status != TENANT_STATUS_ACTIVE
    )
    if leaving_active:
        db.query(User).filter(User.professional_id == professional_id).update(
            {User.auth_version: User.auth_version + 1},
            synchronize_session=False,
        )

    professional.status = target_status
    professional.status_changed_at = now
    professional.status_changed_by = admin_user_id
    professional.status_reason = cleaned_reason

    if target_status == TENANT_STATUS_ACTIVE:
        event_type = _return_to_active_event_type(previous_status)
    else:
        event_type = _EVENT_TYPE_LEAVING_ACTIVE[target_status]

    record_event(
        db,
        professional_id=professional_id,
        event_type=event_type,
        occurred_at=now,
        actor_type="platform_admin",
        actor_id=admin_user_id,
        source_channel="web",
        entity_type="professional",
        entity_id=professional_id,
        correlation_id=uuid.uuid4(),
        payload={
            "reason": cleaned_reason,
            "source_ip": source_ip,
            "user_agent": user_agent[:512] if user_agent else None,
        },
        before_state={"status": previous_status},
        after_state={"status": target_status},
    )
    return professional
