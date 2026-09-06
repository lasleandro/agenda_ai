"""Tests for tenant-scoped generated customers in the dev mock chat."""

from pathlib import Path
import sys
import uuid

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.dependencies import require_platform_admin, require_platform_admin_professional_id
from app.api.dev_mock import _create_mock_customer, _get_mock_customer, router
from app.database import SessionLocal
from app.models import Contact, Conversation, Professional


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().int % 100_000_000:08d}"


DEV_ENDPOINT_PATHS = {
    "/api/dev/mock-conversation",
    "/api/dev/mock-customers",
    "/api/dev/mock-messages",
    "/api/dev/mock-conversation/reset",
    "/api/dev/conversations/{conversation_id}/process-now",
}


def test_dev_mock_endpoints_require_platform_admin_selected_tenant() -> None:
    route_paths = {route.path for route in router.routes}
    assert route_paths == DEV_ENDPOINT_PATHS
    for route in router.routes:
        dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
        assert require_platform_admin_professional_id in dependency_calls


def test_platform_admin_selected_tenant_guard_professional_returns_forbidden() -> None:
    professional = {"role": "professional", "professional_id": str(uuid.uuid4())}

    with pytest.raises(HTTPException) as caught:
        require_platform_admin_professional_id(require_platform_admin(professional))

    assert caught.value.status_code == 403


def test_platform_admin_selected_tenant_guard_unscoped_admin_returns_forbidden() -> None:
    admin = {"role": "platform_admin", "professional_id": None}

    with pytest.raises(HTTPException) as caught:
        require_platform_admin_professional_id(require_platform_admin(admin))

    assert caught.value.status_code == 403


def test_platform_admin_selected_tenant_guard_scoped_admin_returns_tenant_id() -> None:
    professional_id = uuid.uuid4()
    admin = {"role": "platform_admin", "professional_id": str(professional_id)}

    result = require_platform_admin_professional_id(require_platform_admin(admin))

    assert result == professional_id


def test_create_mock_customer_creates_selectable_tenant_conversation_with_unique_name() -> None:
    db = SessionLocal()
    professional = Professional(name="Mock tenant", assistant_phone=_random_phone())
    other_professional = Professional(name="Other tenant", assistant_phone=_random_phone())
    db.add_all([professional, other_professional])
    db.commit()

    try:
        conversation_id, customer_phone, customer_name = _create_mock_customer(db, professional.id)
        second_conversation_id, second_customer_phone, second_customer_name = _create_mock_customer(
            db, professional.id
        )

        assert customer_name.endswith("(mock)")
        assert second_customer_name.endswith("(mock)")
        assert customer_name != second_customer_name
        assert customer_phone != second_customer_phone
        selected_phone, selected_name = _get_mock_customer(
            db, professional.id, customer_phone
        )
        assert selected_phone == customer_phone
        assert selected_name == customer_name
        assert (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.professional_id == professional.id)
            .one()
        )
        assert (
            db.query(Conversation)
            .filter(
                Conversation.id == second_conversation_id,
                Conversation.professional_id == professional.id,
            )
            .one()
        )

        with pytest.raises(HTTPException, match="Mock customer not found"):
            _get_mock_customer(db, other_professional.id, customer_phone)
    finally:
        professional_ids = [professional.id, other_professional.id]
        db.query(Conversation).filter(
            Conversation.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(Contact).filter(Contact.professional_id.in_(professional_ids)).delete(
            synchronize_session=False
        )
        db.query(Professional).filter(Professional.id.in_(professional_ids)).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()
