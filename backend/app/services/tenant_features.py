"""Tenant feature resolution and audited mutation."""

import uuid

from sqlalchemy.orm import Session

from app.models import TenantFeature, TenantFeatureAuditLog

COMMERCIAL_FINANCIALS = "commercial_financials"


def is_tenant_feature_enabled(
    db: Session,
    professional_id: uuid.UUID,
    feature_key: str,
) -> bool:
    """Return false when a tenant has no explicit feature record."""
    enabled = (
        db.query(TenantFeature.enabled)
        .filter(
            TenantFeature.professional_id == professional_id,
            TenantFeature.feature_key == feature_key,
        )
        .scalar()
    )
    return bool(enabled)


def set_tenant_feature(
    db: Session,
    *,
    professional_id: uuid.UUID,
    feature_key: str,
    enabled: bool,
    admin_user_id: uuid.UUID,
    source_ip: str | None,
    user_agent: str | None,
) -> bool:
    """Set a feature and append an audit row only when its value changes."""
    feature = (
        db.query(TenantFeature)
        .filter(
            TenantFeature.professional_id == professional_id,
            TenantFeature.feature_key == feature_key,
        )
        .first()
    )
    previous_enabled = feature.enabled if feature is not None else False
    if previous_enabled == enabled:
        return previous_enabled

    if feature is None:
        feature = TenantFeature(
            professional_id=professional_id,
            feature_key=feature_key,
            enabled=enabled,
            configured_by_user_id=admin_user_id,
        )
        db.add(feature)
    else:
        feature.enabled = enabled
        feature.configured_by_user_id = admin_user_id

    db.add(
        TenantFeatureAuditLog(
            professional_id=professional_id,
            feature_key=feature_key,
            admin_user_id=admin_user_id,
            previous_enabled=previous_enabled,
            new_enabled=enabled,
            source_ip=source_ip[:64] if source_ip else None,
            user_agent=user_agent[:512] if user_agent else None,
        )
    )
    return enabled
