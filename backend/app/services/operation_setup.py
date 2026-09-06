"""First-session setup state for a tenant.

A tenant's operation counts as configured once it has at least one Local
(``Place``) and at least one work interval in the weekly journey. These are
the two setup surfaces every tenant has regardless of feature flags, and the
minimum for the Agenda and capacity views to be meaningful. Financial rates
are intentionally excluded: they are gated by ``commercial_financials`` and
are advisory, so a tenant without the feature could never satisfy them.
"""

import uuid

from sqlalchemy.orm import Session

from app.models import Place, WorkJourneyInterval

WORK_INTERVAL_TYPE = "work"


def operation_is_configured(db: Session, professional_id: uuid.UUID) -> bool:
    """Return whether the tenant has completed first-session setup."""
    has_place = (
        db.query(Place.id)
        .filter(Place.professional_id == professional_id)
        .first()
        is not None
    )
    if not has_place:
        return False

    has_work_interval = (
        db.query(WorkJourneyInterval.id)
        .filter(
            WorkJourneyInterval.professional_id == professional_id,
            WorkJourneyInterval.interval_type == WORK_INTERVAL_TYPE,
        )
        .first()
        is not None
    )
    return has_work_interval
