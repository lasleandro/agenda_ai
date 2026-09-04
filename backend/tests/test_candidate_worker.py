"""Claim-lease recovery behaviour for the appointment candidate worker."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.chat.candidate_worker as worker
from app.database import SessionLocal
from app.models import Contact, Conversation, Message, OperationalEvent, PendingProcessing, Professional
from app.chat.ingestion import ingest_normalized_message
from app.chat.ycloud_provider import NormalizedMessage


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().int % 100_000_000:08d}"


def _inbound(assistant_phone: str, customer_phone: str) -> NormalizedMessage:
    return NormalizedMessage(
        provider_message_id=f"msg_{uuid.uuid4().hex}",
        direction="inbound",
        from_phone=customer_phone,
        to_phone=assistant_phone,
        text="Oi, posso marcar aula?",
        sent_at=datetime.now(timezone.utc),
        raw_payload={},
    )


def _make_due_conversation(db) -> tuple[Professional, uuid.UUID]:
    professional = Professional(name="Tenant Worker", assistant_phone=_random_phone())
    db.add(professional)
    db.commit()
    message = ingest_normalized_message(
        db, _inbound(professional.assistant_phone, _random_phone())
    )
    # Make the debounce window due now.
    db.query(PendingProcessing).filter(
        PendingProcessing.conversation_id == message.conversation_id
    ).update(
        {"process_after": datetime.now(timezone.utc) - timedelta(seconds=1)},
        synchronize_session=False,
    )
    db.commit()
    return professional, message.conversation_id


def _cleanup(db, professional_id) -> None:
    db.query(OperationalEvent).filter(
        OperationalEvent.professional_id == professional_id
    ).delete(synchronize_session=False)
    conversation_ids = [
        row[0]
        for row in db.query(Conversation.id)
        .filter(Conversation.professional_id == professional_id)
        .all()
    ]
    if conversation_ids:
        db.query(PendingProcessing).filter(
            PendingProcessing.conversation_id.in_(conversation_ids)
        ).delete(synchronize_session=False)
    db.query(Message).filter(Message.professional_id == professional_id).delete(
        synchronize_session=False
    )
    db.query(Conversation).filter(
        Conversation.professional_id == professional_id
    ).delete(synchronize_session=False)
    db.query(Contact).filter(Contact.professional_id == professional_id).delete(
        synchronize_session=False
    )
    db.query(Professional).filter(Professional.id == professional_id).delete(
        synchronize_session=False
    )
    db.commit()


def test_failed_extraction_keeps_a_claimed_row_so_work_is_not_lost(monkeypatch) -> None:
    db = SessionLocal()
    professional, conversation_id = _make_due_conversation(db)
    try:
        def boom(_db, _conversation):
            raise RuntimeError("extraction blew up")

        monkeypatch.setattr(worker, "process_conversation", boom)
        worker.process_due_conversations()

        db.expire_all()
        row = (
            db.query(PendingProcessing)
            .filter(PendingProcessing.conversation_id == conversation_id)
            .one()
        )
        assert row.claimed_at is not None
        assert row.attempts == 1
    finally:
        _cleanup(db, professional.id)
        db.close()


def test_stale_claim_is_reclaimed_and_success_deletes_the_row(monkeypatch) -> None:
    db = SessionLocal()
    professional, conversation_id = _make_due_conversation(db)
    try:
        monkeypatch.setattr(
            worker, "process_conversation", lambda _db, _c: (_ for _ in ()).throw(RuntimeError())
        )
        worker.process_due_conversations()

        # Age the claim past the lease so it is reclaimable.
        db.query(PendingProcessing).filter(
            PendingProcessing.conversation_id == conversation_id
        ).update(
            {
                "claimed_at": datetime.now(timezone.utc)
                - timedelta(seconds=worker.CLAIM_LEASE_SECONDS + 60)
            },
            synchronize_session=False,
        )
        db.commit()

        monkeypatch.setattr(worker, "process_conversation", lambda _db, _c: [])
        worker.process_due_conversations()

        db.expire_all()
        assert (
            db.query(PendingProcessing)
            .filter(PendingProcessing.conversation_id == conversation_id)
            .first()
            is None
        )
    finally:
        _cleanup(db, professional.id)
        db.close()


def test_poison_conversation_is_dropped_after_max_attempts(monkeypatch) -> None:
    db = SessionLocal()
    professional, conversation_id = _make_due_conversation(db)
    try:
        db.query(PendingProcessing).filter(
            PendingProcessing.conversation_id == conversation_id
        ).update(
            {"attempts": worker.MAX_ATTEMPTS - 1, "claimed_at": None},
            synchronize_session=False,
        )
        db.commit()

        monkeypatch.setattr(
            worker, "process_conversation", lambda _db, _c: (_ for _ in ()).throw(RuntimeError())
        )
        worker.process_due_conversations()

        db.expire_all()
        assert (
            db.query(PendingProcessing)
            .filter(PendingProcessing.conversation_id == conversation_id)
            .first()
            is None
        )
    finally:
        _cleanup(db, professional.id)
        db.close()
