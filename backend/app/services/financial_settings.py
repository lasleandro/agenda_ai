"""Shared read/write helpers for ProfessionalFinancialSettings fields
that are configured outside the Financeiro module (e.g. cancellation
notice hours, which every tenant needs regardless of the
commercial_financials feature flag)."""

import uuid

from sqlalchemy.orm import Session

from app.models.professional_financial_settings import ProfessionalFinancialSettings

DEFAULT_CANCELLATION_NOTICE_HOURS = 24


def get_cancellation_notice_hours(db: Session, professional_id: uuid.UUID) -> int:
    settings = (
        db.query(ProfessionalFinancialSettings)
        .filter(ProfessionalFinancialSettings.professional_id == professional_id)
        .first()
    )
    return (
        settings.cancellation_notice_hours
        if settings
        else DEFAULT_CANCELLATION_NOTICE_HOURS
    )


def update_cancellation_notice_hours(
    db: Session,
    professional_id: uuid.UUID,
    hours: int,
) -> int:
    settings = (
        db.query(ProfessionalFinancialSettings)
        .filter(ProfessionalFinancialSettings.professional_id == professional_id)
        .first()
    )
    previous_hours = (
        settings.cancellation_notice_hours
        if settings
        else DEFAULT_CANCELLATION_NOTICE_HOURS
    )
    if settings is None:
        settings = ProfessionalFinancialSettings(professional_id=professional_id)
        db.add(settings)
    settings.cancellation_notice_hours = hours
    return previous_hours
