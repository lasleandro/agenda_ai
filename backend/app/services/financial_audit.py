"""Financial audit helper shared by configuration and override writes."""

import uuid

from sqlalchemy.orm import Session

from app.models import FinancialChangeAuditLog


def add_financial_audit(
    db: Session,
    *,
    professional_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID | None,
    action: str,
    changes: dict,
    source_ip: str | None,
    user_agent: str | None,
) -> None:
    if not changes:
        return
    db.add(
        FinancialChangeAuditLog(
            professional_id=professional_id,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            changes=changes,
            source_ip=source_ip[:64] if source_ip else None,
            user_agent=user_agent[:512] if user_agent else None,
        )
    )
