"""Tests for tenant-scoped generated customers in the dev mock chat."""

from pathlib import Path
import sys
import uuid

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.dev_mock import _create_mock_customer, _get_mock_customer
from app.database import SessionLocal
from app.models import Contact, Conversation, Professional


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().hex[:8]}"


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
