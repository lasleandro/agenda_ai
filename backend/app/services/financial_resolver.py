"""Pure inheritance rules plus tenant financial lookups."""

import uuid

from sqlalchemy.orm import Session

from app.models import PlaceFinancialRate, ProfessionalFinancialSettings


def get_default_commercial_status(db: Session, professional_id: uuid.UUID) -> str:
    status = (
        db.query(ProfessionalFinancialSettings.default_commercial_status)
        .filter(ProfessionalFinancialSettings.professional_id == professional_id)
        .scalar()
    )
    return status or "active"


def get_global_hourly_rate(
    db: Session,
    professional_id: uuid.UUID,
    participant_count: int,
    time_category: str = "regular",
) -> int | None:
    """The tenant-wide default rate (unified matrix's ``place_id IS NULL``
    row). Time-agnostic callers (customer/group detail cards) default to
    the ``regular`` row, matching the pre-unification behavior."""
    if participant_count < 1 or participant_count > 4:
        return None
    return (
        db.query(PlaceFinancialRate.hourly_rate_cents)
        .filter(
            PlaceFinancialRate.professional_id == professional_id,
            PlaceFinancialRate.place_id.is_(None),
            PlaceFinancialRate.time_category == time_category,
            PlaceFinancialRate.participant_count == participant_count,
        )
        .scalar()
    )


def resolve_commercial_status(
    *,
    customer_status: str | None,
    group_status: str | None,
    tenant_status: str,
) -> tuple[str, str]:
    if customer_status is not None:
        return customer_status, "customer"
    if group_status is not None:
        return group_status, "group"
    return tenant_status, "tenant"


def resolve_hourly_rate(
    *,
    customer_rate_cents: int | None,
    group_rate_cents: int | None,
    place_rate_cents: int | None = None,
    tenant_rate_cents: int | None,
) -> tuple[int | None, str]:
    if customer_rate_cents is not None:
        return customer_rate_cents, "customer"
    if group_rate_cents is not None:
        return group_rate_cents, "group"
    if place_rate_cents is not None:
        return place_rate_cents, "place"
    if tenant_rate_cents is not None:
        return tenant_rate_cents, "tenant"
    return None, "unset"
