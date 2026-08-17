"""Integration tests for tenant-isolated daily agenda scheduling."""

from datetime import datetime, time, timedelta, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.integrations.whatsapp.contracts import (
    WhatsAppDeliveryUpdated,
    WhatsAppSendResult,
    WhatsAppTemplateRequest,
)
from app.models import OperationalEvent, Professional, ScheduledTask, ScheduledTaskRun, User
from app.models.scheduled_task import DAILY_AGENDA_SUMMARY
from app.services.scheduled_tasks import (
    ScheduledTaskConfigurationError,
    apply_delivery_update,
    process_due_scheduled_tasks,
    update_daily_agenda_task,
)


class _FakeWhatsAppProvider:
    key = "fake"

    def __init__(self) -> None:
        self.requests: list[WhatsAppTemplateRequest] = []

    def send_template(self, request: WhatsAppTemplateRequest) -> WhatsAppSendResult:
        self.requests.append(request)
        return WhatsAppSendResult(
            provider_key=self.key,
            provider_message_id=f"message-{len(self.requests)}",
            accepted_at=datetime.now(timezone.utc),
            external_id=request.external_id,
        )


def _professional(name: str) -> Professional:
    token = uuid.uuid4().hex[:8]
    return Professional(
        name=name,
        timezone="America/Sao_Paulo",
        agent_phone=f"+55119888{token}",
        assistant_phone=f"+55119777{token}",
    )


def _cleanup(
    db, professional_ids: list[uuid.UUID], user_ids: list[uuid.UUID] | None = None
) -> None:
    task_ids = [
        row[0]
        for row in db.query(ScheduledTask.id)
        .filter(ScheduledTask.professional_id.in_(professional_ids))
        .all()
    ]
    if task_ids:
        db.query(ScheduledTaskRun).filter(
            ScheduledTaskRun.scheduled_task_id.in_(task_ids)
        ).delete(synchronize_session=False)
    db.query(ScheduledTask).filter(
        ScheduledTask.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(OperationalEvent).filter(
        OperationalEvent.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    if user_ids:
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    db.query(Professional).filter(Professional.id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.commit()


def test_daily_agenda_task_sends_once_for_its_own_tenant() -> None:
    db = SessionLocal()
    now = datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)
    target = _professional("Scheduled tenant")
    other = _professional("Other tenant")
    db.add_all([target, other])
    db.flush()
    target_task = ScheduledTask(
        professional_id=target.id,
        task_type=DAILY_AGENDA_SUMMARY,
        enabled=True,
        local_time=time(7, 0),
        enabled_at=now - timedelta(days=1),
    )
    other_task = ScheduledTask(
        professional_id=other.id,
        task_type=DAILY_AGENDA_SUMMARY,
        enabled=True,
        local_time=time(7, 0),
        enabled_at=now,
    )
    db.add_all([target_task, other_task])
    db.commit()
    provider = _FakeWhatsAppProvider()

    try:
        assert process_due_scheduled_tasks(db, provider, now) == 1
        assert process_due_scheduled_tasks(db, provider, now) == 0
        assert len(provider.requests) == 1
        assert provider.requests[0].from_phone == target.agent_phone
        assert provider.requests[0].to_phone == target.assistant_phone
        assert provider.requests[0].template_key == "daily_agenda"

        run = db.query(ScheduledTaskRun).filter_by(scheduled_task_id=target_task.id).one()
        assert run.professional_id == target.id
        assert run.status == "provider_accepted"
        assert db.query(ScheduledTaskRun).filter_by(scheduled_task_id=other_task.id).count() == 0
    finally:
        _cleanup(db, [target.id, other.id])
        db.close()


def test_delivery_update_matches_provider_and_never_regresses_state() -> None:
    db = SessionLocal()
    professional = _professional("Delivery tenant")
    db.add(professional)
    db.flush()
    task = ScheduledTask(professional_id=professional.id, task_type=DAILY_AGENDA_SUMMARY)
    db.add(task)
    db.flush()
    run = ScheduledTaskRun(
        professional_id=professional.id,
        scheduled_task_id=task.id,
        target_local_date=datetime(2026, 8, 17).date(),
        scheduled_for_at=datetime(2026, 8, 17, 10, tzinfo=timezone.utc),
        status="provider_accepted",
        provider_key="fake",
        provider_message_id="message-1",
    )
    db.add(run)
    db.commit()

    try:
        assert not apply_delivery_update(
            db,
            WhatsAppDeliveryUpdated(
                provider_key="other-provider",
                provider_message_id="message-1",
                status="delivered",
                occurred_at=datetime.now(timezone.utc),
            ),
        )
        assert apply_delivery_update(
            db,
            WhatsAppDeliveryUpdated(
                provider_key="fake",
                provider_message_id="message-1",
                status="delivered",
                occurred_at=datetime.now(timezone.utc),
            ),
        )
        assert apply_delivery_update(
            db,
            WhatsAppDeliveryUpdated(
                provider_key="fake",
                provider_message_id="message-1",
                status="sent",
                occurred_at=datetime.now(timezone.utc),
            ),
        )
        db.refresh(run)
        assert run.status == "delivered"
    finally:
        _cleanup(db, [professional.id])
        db.close()


def test_daily_agenda_configuration_requires_consent_and_records_audit_event() -> None:
    db = SessionLocal()
    professional = _professional("Configured tenant")
    admin = User(
        email=f"{uuid.uuid4().hex}@example.test",
        hashed_password="test-only",
        role="platform_admin",
    )
    db.add_all([professional, admin])
    db.commit()

    try:
        try:
            update_daily_agenda_task(
                db,
                professional_id=professional.id,
                enabled=True,
                local_time=time(7, 30),
                consent_confirmed=False,
                admin_user_id=admin.id,
                source_ip="127.0.0.1",
                user_agent="pytest",
            )
        except ScheduledTaskConfigurationError as exc:
            assert "consent" in str(exc).casefold()
        else:
            raise AssertionError("Expected consent validation to reject the configuration")

        task = update_daily_agenda_task(
            db,
            professional_id=professional.id,
            enabled=True,
            local_time=time(7, 30),
            consent_confirmed=True,
            admin_user_id=admin.id,
            source_ip="127.0.0.1",
            user_agent="pytest",
        )
        db.commit()

        assert task.enabled is True
        assert task.consent_confirmed_at is not None
        event = (
            db.query(OperationalEvent)
            .filter_by(
                professional_id=professional.id,
                event_type="scheduled_task.configuration.updated",
            )
            .one()
        )
        assert event.actor_id == admin.id
    finally:
        _cleanup(db, [professional.id], [admin.id])
        db.close()
