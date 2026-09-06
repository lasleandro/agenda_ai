"""Tests for the deterministic WhatsApp agent channel (AI Agent Operations
Roadmap v0.1, Phase 0)."""

from pathlib import Path
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent import candidates
from app.agent.orchestrator import AgentResponse, PendingCandidate
from app.chat import agent_channel
from app.chat.ingestion import dispatch_whatsapp_event
from app.chat.ycloud_provider import NormalizedMessage
from app.core.security import hash_password
from app.database import SessionLocal
from app.models import (
    AgentChannelMessage,
    Appointment,
    Contact,
    Conversation,
    MakeupClassCredit,
    Message,
    OperationalEvent,
    OperatorActionCandidate,
    PendingProcessing,
    Professional,
    ScheduleOccurrenceOverride,
    User,
)
from app.services.scheduling import TIMEZONE

PLATFORM_NUMBER = "+5511970000000"


@pytest.fixture(autouse=True)
def _platform_agent_number(monkeypatch):
    """Every agent-channel test runs with the shared platform number set."""
    monkeypatch.setenv("PLATFORM_AGENT_WHATSAPP_NUMBER", PLATFORM_NUMBER)


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().int % 100_000_000:08d}"


def _random_email() -> str:
    return f"agent_channel_{uuid.uuid4().hex[:10]}@agenda.ai"


def _make_professional(db, **overrides) -> Professional:
    fields = {
        "name": "Tenant Agent Channel",
        "assistant_phone": _random_phone(),
        # Most agent-channel tests assume an already-bound channel; the
        # binding-gate tests pass agent_binding_confirmed_at=None explicitly.
        "agent_binding_confirmed_at": datetime.now(timezone.utc),
        **overrides,
    }
    professional = Professional(**fields)
    db.add(professional)
    db.commit()
    return professional


def _make_operator_user(db, professional_id) -> User:
    user = User(
        email=_random_email(),
        hashed_password=hash_password("correct-password"),
        role="professional",
        professional_id=professional_id,
    )
    db.add(user)
    db.commit()
    return user


def _make_contact(db, professional_id, name: str = "Aluno") -> Contact:
    contact = Contact(
        professional_id=professional_id,
        phone=_random_phone(),
        display_name=name,
        normalized_name=name.casefold(),
    )
    db.add(contact)
    db.commit()
    return contact


def _inbound_msg(to_phone: str, from_phone: str, text: str) -> NormalizedMessage:
    return NormalizedMessage(
        provider_message_id=f"msg_{uuid.uuid4().hex}",
        direction="inbound",
        from_phone=from_phone,
        to_phone=to_phone,
        text=text,
        sent_at=datetime.now(timezone.utc),
        raw_payload={},
    )


def _inbound_to_agent(instructor_phone: str, text: str) -> NormalizedMessage:
    """A message the instructor sends to the shared platform agent number."""
    return _inbound_msg(PLATFORM_NUMBER, instructor_phone, text)


def _cleanup(db, *, professionals: list[Professional]) -> None:
    professional_ids = [p.id for p in professionals]
    if not professional_ids:
        return
    conversation_ids = [
        row[0]
        for row in db.query(Conversation.id)
        .filter(Conversation.professional_id.in_(professional_ids))
        .all()
    ]
    if conversation_ids:
        db.query(PendingProcessing).filter(
            PendingProcessing.conversation_id.in_(conversation_ids)
        ).delete(synchronize_session=False)
    db.query(Message).filter(Message.professional_id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.query(Conversation).filter(
        Conversation.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(MakeupClassCredit).filter(
        MakeupClassCredit.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(ScheduleOccurrenceOverride).filter(
        ScheduleOccurrenceOverride.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(Appointment).filter(Appointment.professional_id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.query(Contact).filter(Contact.professional_id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.query(AgentChannelMessage).filter(
        AgentChannelMessage.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(OperationalEvent).filter(
        OperationalEvent.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(OperatorActionCandidate).filter(
        OperatorActionCandidate.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(User).filter(User.professional_id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.query(Professional).filter(Professional.id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.commit()


def test_normalize_command_strips_accents_case_and_padding() -> None:
    assert agent_channel.normalize_command("  PRÓXIMA   Aula ") == "proxima aula"
    assert agent_channel.normalize_command("Amanhã") == "amanha"


def test_try_handle_sends_reply_and_does_not_touch_customer_pipeline(monkeypatch) -> None:
    """A message to the platform agent number must never create a Contact/
    Conversation/Message row — that's the customer-facing pipeline's job."""
    db = SessionLocal()
    professional = _make_professional(db)

    sent: dict = {}

    def _fake_send(from_phone: str, to_phone: str, body: str) -> None:
        sent["from_phone"] = from_phone
        sent["to_phone"] = to_phone
        sent["body"] = body

    monkeypatch.setattr(agent_channel, "send_text_message", _fake_send)

    try:
        instructor_phone = professional.assistant_phone
        handled = agent_channel.try_handle(
            db, _inbound_to_agent(instructor_phone, "hoje")
        )

        assert handled is True
        assert sent["from_phone"] == PLATFORM_NUMBER
        assert sent["to_phone"] == instructor_phone
        assert "Aulas de hoje" in sent["body"]

        assert db.query(Contact).filter(Contact.professional_id == professional.id).count() == 0
        assert (
            db.query(Conversation).filter(Conversation.professional_id == professional.id).count()
            == 0
        )
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_try_handle_drops_messages_from_unrecognized_senders(monkeypatch) -> None:
    """The tenant is resolved from the sender. A message to the platform
    number from a phone that is no active tenant's assistant_phone is claimed
    (return True) and silently dropped — never treated as some instructor."""
    db = SessionLocal()
    professional = _make_professional(db)

    sent: dict = {}
    monkeypatch.setattr(
        agent_channel, "send_text_message", lambda **kwargs: sent.update(kwargs)
    )

    try:
        handled = agent_channel.try_handle(
            db, _inbound_to_agent(_random_phone(), "hoje")
        )
        assert handled is True
        assert sent == {}
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_try_handle_does_not_match_a_tenant_with_null_assistant_phone(monkeypatch) -> None:
    """Fail closed: a tenant with no assistant_phone on file cannot be
    resolved as the sender, so it can never reach the agent channel."""
    db = SessionLocal()
    professional = _make_professional(db, assistant_phone=None)

    sent: dict = {}
    monkeypatch.setattr(
        agent_channel, "send_text_message", lambda **kwargs: sent.update(kwargs)
    )

    try:
        handled = agent_channel.try_handle(
            db, _inbound_to_agent(_random_phone(), "hoje")
        )
        assert handled is True
        assert sent == {}
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_try_handle_returns_false_when_not_addressed_to_the_platform_number() -> None:
    """A message to any number other than the platform agent number must fall
    through to the caller's normal (customer-facing) routing."""
    db = SessionLocal()
    try:
        handled = agent_channel.try_handle(
            db, _inbound_msg(_random_phone(), _random_phone(), "hoje")
        )
        assert handled is False
    finally:
        db.close()


def test_dispatch_claims_agent_number_away_from_passive_pipeline(monkeypatch) -> None:
    """An inbound message to the platform number from a known instructor is
    claimed by the agent channel: dispatch returns None and nothing is
    persisted to the customer-facing tables."""
    db = SessionLocal()
    professional = _make_professional(db)
    monkeypatch.setattr(agent_channel, "send_text_message", lambda **kwargs: None)

    try:
        result = dispatch_whatsapp_event(
            db, _inbound_to_agent(professional.assistant_phone, "hoje"), None
        )
        assert result is None
        assert (
            db.query(Contact).filter(Contact.professional_id == professional.id).count()
            == 0
        )
        assert (
            db.query(Conversation)
            .filter(Conversation.professional_id == professional.id)
            .count()
            == 0
        )
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_unbound_tenant_message_is_claimed_and_dropped_without_reply(monkeypatch) -> None:
    """Until the channel is bound, the only message it acts on is the code."""
    db = SessionLocal()
    professional = _make_professional(db, agent_binding_confirmed_at=None)
    _make_operator_user(db, professional.id)
    sent: dict = {}
    monkeypatch.setattr(
        agent_channel, "send_text_message", lambda **kwargs: sent.update(kwargs)
    )
    try:
        handled = agent_channel.try_handle(
            db, _inbound_to_agent(professional.assistant_phone, "hoje")
        )
        assert handled is True
        assert sent == {}
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_unbound_tenant_binds_when_it_sends_the_challenge_code(monkeypatch) -> None:
    from app.services import agent_binding

    db = SessionLocal()
    professional = _make_professional(db, agent_binding_confirmed_at=None)
    _make_operator_user(db, professional.id)
    sent: dict = {}
    monkeypatch.setattr(
        agent_channel,
        "send_text_message",
        lambda from_phone, to_phone, body: sent.update(body=body),
    )
    try:
        issued = agent_binding.issue_challenge(db, professional.id)
        handled = agent_channel.try_handle(
            db, _inbound_to_agent(professional.assistant_phone, issued.code)
        )
        assert handled is True
        assert "ativado" in sent["body"].lower()
        db.refresh(professional)
        assert professional.agent_binding_confirmed_at is not None
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_handle_hoje_lists_todays_appointments(monkeypatch) -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    contact = _make_contact(db, professional.id, "Mariana")

    now = datetime.now(TIMEZONE)
    appointment = Appointment(
        professional_id=professional.id,
        contact_id=contact.id,
        service="Aula individual",
        start_at=now.replace(hour=9, minute=0, second=0, microsecond=0),
        end_at=now.replace(hour=10, minute=0, second=0, microsecond=0),
        status="confirmed",
        source="dashboard",
    )
    db.add(appointment)
    db.commit()

    sent: dict = {}
    monkeypatch.setattr(
        agent_channel, "send_text_message", lambda from_phone, to_phone, body: sent.update(body=body)
    )

    try:
        handled = agent_channel.try_handle(
            db, _inbound_to_agent(professional.assistant_phone, "hoje")
        )
        assert handled is True
        assert "09:00" in sent["body"]
        assert "Mariana" in sent["body"]
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_unrecognized_text_falls_through_to_the_orchestrator(monkeypatch) -> None:
    """Free-form text that isn't a Phase 0 command or a sim/nao reply must go
    through the same tool-calling orchestrator as the web chat, not a static
    help message — this is the WhatsApp/web-chat parity decision."""
    db = SessionLocal()
    professional = _make_professional(db)
    operator = _make_operator_user(db, professional.id)

    captured: dict = {}

    def _fake_run_agent_turn(db_arg, professional_id, actor_user_id, messages, channel="web"):
        captured["professional_id"] = professional_id
        captured["actor_user_id"] = actor_user_id
        captured["messages"] = messages
        captured["channel"] = channel
        return AgentResponse(reply="Voce tem 2 aulas amanha.")

    monkeypatch.setattr(agent_channel, "run_agent_turn", _fake_run_agent_turn)
    sent: dict = {}
    monkeypatch.setattr(
        agent_channel, "send_text_message", lambda from_phone, to_phone, body: sent.update(body=body)
    )

    try:
        handled = agent_channel.try_handle(
            db,
            _inbound_to_agent(
                professional.assistant_phone, "quantas aulas tenho amanha?"
            ),
        )
        assert handled is True
        assert sent["body"] == "Voce tem 2 aulas amanha."
        assert captured["professional_id"] == professional.id
        assert captured["actor_user_id"] == operator.id
        assert captured["channel"] == "whatsapp"
        assert captured["messages"] == [
            {"role": "user", "content": "quantas aulas tenho amanha?"}
        ]
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_pending_candidate_appends_confirmation_prompt(monkeypatch) -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    _make_operator_user(db, professional.id)

    pending = PendingCandidate(
        id=uuid.uuid4(),
        preview_text="Cancelar aula de Joao amanha as 10h.",
        affected_entities=[],
        expires_at=datetime.now(TIMEZONE),
        advisory_text="Fora da sua jornada configurada. O agendamento pode continuar, mas revise o horário antes de confirmar.",
    )
    monkeypatch.setattr(
        agent_channel,
        "run_agent_turn",
        lambda *a, **k: AgentResponse(reply="Vou cancelar essa aula.", pending_candidate=pending),
    )
    sent: dict = {}
    monkeypatch.setattr(
        agent_channel, "send_text_message", lambda from_phone, to_phone, body: sent.update(body=body)
    )

    try:
        agent_channel.try_handle(
            db,
            _inbound_to_agent(
                professional.assistant_phone, "cancela a aula do Joao amanha"
            ),
        )
        assert "Vou cancelar essa aula." in sent["body"]
        assert "Cancelar aula de Joao amanha as 10h." in sent["body"]
        assert "Fora da sua jornada configurada." in sent["body"]
        assert "sim" in sent["body"].lower()
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_pending_candidate_prompt_lists_every_proposal_from_the_same_turn(monkeypatch) -> None:
    """A single instructor request can produce more than one proposal (e.g.
    cancelling two same-day occurrences) — the confirmation prompt must show
    all of them, not just the first, or the instructor confirms something
    they didn't fully see."""
    db = SessionLocal()
    professional = _make_professional(db)
    operator = _make_operator_user(db, professional.id)
    correlation_id = uuid.uuid4()

    first = OperatorActionCandidate(
        professional_id=professional.id,
        actor_user_id=operator.id,
        channel="whatsapp",
        tool_name="propose_cancel_schedule",
        resolved_arguments={},
        preview_text="Cancelar aula das 9h de Joao.",
        affected_entities=[],
        status="proposed",
        expires_at=datetime.now(TIMEZONE) + timedelta(minutes=10),
        correlation_id=correlation_id,
    )
    second = OperatorActionCandidate(
        professional_id=professional.id,
        actor_user_id=operator.id,
        channel="whatsapp",
        tool_name="propose_cancel_schedule",
        resolved_arguments={},
        preview_text="Cancelar aula das 15h de Joao.",
        affected_entities=[],
        status="proposed",
        expires_at=datetime.now(TIMEZONE) + timedelta(minutes=10),
        correlation_id=correlation_id,
    )
    db.add_all([first, second])
    db.commit()

    pending = PendingCandidate(
        id=first.id,
        preview_text=first.preview_text,
        affected_entities=[],
        expires_at=first.expires_at,
    )
    monkeypatch.setattr(
        agent_channel,
        "run_agent_turn",
        lambda *a, **k: AgentResponse(reply="Vou cancelar as duas aulas.", pending_candidate=pending),
    )
    sent: dict = {}
    monkeypatch.setattr(
        agent_channel, "send_text_message", lambda from_phone, to_phone, body: sent.update(body=body)
    )

    try:
        agent_channel.try_handle(
            db,
            _inbound_to_agent(
                professional.assistant_phone, "cancela as duas aulas de hoje"
            ),
        )
        assert "Cancelar aula das 9h de Joao." in sent["body"]
        assert "Cancelar aula das 15h de Joao." in sent["body"]
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_sim_confirms_every_pending_candidate_from_the_same_turn() -> None:
    """Regression test for the reported bug: two same-turn proposals must
    both execute on a single 'sim', not just the most recently created one."""
    db = SessionLocal()
    professional = _make_professional(db)
    operator = _make_operator_user(db, professional.id)
    correlation_id = uuid.uuid4()

    contact = _make_contact(db, professional.id, "Joao")
    now = datetime.now(TIMEZONE)
    appt_1 = Appointment(
        professional_id=professional.id,
        contact_id=contact.id,
        service="Aula individual",
        start_at=now.replace(hour=9, minute=0, second=0, microsecond=0),
        end_at=now.replace(hour=10, minute=0, second=0, microsecond=0),
        status="confirmed",
        source="dashboard",
    )
    appt_2 = Appointment(
        professional_id=professional.id,
        contact_id=contact.id,
        service="Aula individual",
        start_at=now.replace(hour=15, minute=0, second=0, microsecond=0),
        end_at=now.replace(hour=16, minute=0, second=0, microsecond=0),
        status="confirmed",
        source="dashboard",
    )
    db.add_all([appt_1, appt_2])
    db.commit()

    first = OperatorActionCandidate(
        professional_id=professional.id,
        actor_user_id=operator.id,
        channel="whatsapp",
        tool_name="propose_cancel_schedule",
        resolved_arguments={
            "target_type": "appointment",
            "target_id": str(appt_1.id),
            "occurrence_date": now.date().isoformat(),
        },
        preview_text="Cancelar aula das 9h de Joao.",
        affected_entities=[],
        status="proposed",
        expires_at=now + timedelta(minutes=10),
        correlation_id=correlation_id,
    )
    second = OperatorActionCandidate(
        professional_id=professional.id,
        actor_user_id=operator.id,
        channel="whatsapp",
        tool_name="propose_cancel_schedule",
        resolved_arguments={
            "target_type": "appointment",
            "target_id": str(appt_2.id),
            "occurrence_date": now.date().isoformat(),
        },
        preview_text="Cancelar aula das 15h de Joao.",
        affected_entities=[],
        status="proposed",
        expires_at=now + timedelta(minutes=10),
        correlation_id=correlation_id,
    )
    db.add_all([first, second])
    db.commit()

    try:
        agent_channel._handle_confirmation_reply(db, professional, operator.id, "sim")

        db.refresh(first)
        db.refresh(second)
        assert first.status == "executed"
        assert second.status == "executed"
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_nao_rejects_every_pending_candidate_from_the_same_turn() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    operator = _make_operator_user(db, professional.id)
    correlation_id = uuid.uuid4()

    first = OperatorActionCandidate(
        professional_id=professional.id,
        actor_user_id=operator.id,
        channel="whatsapp",
        tool_name="propose_cancel_schedule",
        resolved_arguments={},
        preview_text="Cancelar aula das 9h de Joao.",
        affected_entities=[],
        status="proposed",
        expires_at=datetime.now(TIMEZONE) + timedelta(minutes=10),
        correlation_id=correlation_id,
    )
    second = OperatorActionCandidate(
        professional_id=professional.id,
        actor_user_id=operator.id,
        channel="whatsapp",
        tool_name="propose_cancel_schedule",
        resolved_arguments={},
        preview_text="Cancelar aula das 15h de Joao.",
        affected_entities=[],
        status="proposed",
        expires_at=datetime.now(TIMEZONE) + timedelta(minutes=10),
        correlation_id=correlation_id,
    )
    db.add_all([first, second])
    db.commit()

    try:
        reply = agent_channel._handle_confirmation_reply(db, professional, operator.id, "nao")
        db.refresh(first)
        db.refresh(second)
        assert first.status == "rejected"
        assert second.status == "rejected"
        assert "2" in reply
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_sim_confirms_the_latest_pending_whatsapp_candidate(monkeypatch) -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    operator = _make_operator_user(db, professional.id)

    executed: dict = {}
    monkeypatch.setattr(
        candidates,
        "confirm",
        lambda db_arg, professional_id, actor_user_id, candidate_id: executed.update(
            candidate_id=candidate_id
        )
        or candidates.ExecutionResult(ok=True, summary="Aula cancelada."),
    )
    sent: dict = {}
    monkeypatch.setattr(
        agent_channel, "send_text_message", lambda from_phone, to_phone, body: sent.update(body=body)
    )

    candidate = OperatorActionCandidate(
        professional_id=professional.id,
        actor_user_id=operator.id,
        channel="whatsapp",
        tool_name="propose_cancel_schedule",
        resolved_arguments={},
        preview_text="Cancelar aula de Joao amanha as 10h.",
        affected_entities=[],
        status="proposed",
        expires_at=datetime.now(TIMEZONE) + timedelta(minutes=10),
        correlation_id=uuid.uuid4(),
    )
    db.add(candidate)
    db.commit()

    try:
        agent_channel.try_handle(
            db, _inbound_to_agent(professional.assistant_phone, "sim")
        )
        assert executed["candidate_id"] == candidate.id
        assert sent["body"] == "Aula cancelada."
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_nao_rejects_the_latest_pending_whatsapp_candidate(monkeypatch) -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    operator = _make_operator_user(db, professional.id)
    monkeypatch.setattr(agent_channel, "send_text_message", lambda **kwargs: None)

    candidate = OperatorActionCandidate(
        professional_id=professional.id,
        actor_user_id=operator.id,
        channel="whatsapp",
        tool_name="propose_cancel_schedule",
        resolved_arguments={},
        preview_text="Cancelar aula de Joao amanha as 10h.",
        affected_entities=[],
        status="proposed",
        expires_at=datetime.now(TIMEZONE) + timedelta(minutes=10),
        correlation_id=uuid.uuid4(),
    )
    db.add(candidate)
    db.commit()

    try:
        agent_channel.try_handle(
            db, _inbound_to_agent(professional.assistant_phone, "nao")
        )
        db.refresh(candidate)
        assert candidate.status == "rejected"
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_sim_with_no_pending_candidate_says_so() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    _make_operator_user(db, professional.id)

    try:
        reply = agent_channel._handle_confirmation_reply(
            db, professional, uuid.uuid4(), "sim"
        )
        assert "nao ha nenhuma acao pendente" in agent_channel.normalize_command(reply)
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_agent_turn_persists_and_replays_conversation_history(monkeypatch) -> None:
    """A second free-text message must see the first exchange as prior
    context — this is Phase 3 (multi-turn conversation state)."""
    db = SessionLocal()
    professional = _make_professional(db)
    _make_operator_user(db, professional.id)
    instructor_phone = professional.assistant_phone

    captured_messages: list[list[dict]] = []

    def _fake_run_agent_turn(db_arg, professional_id, actor_user_id, messages, channel="web"):
        captured_messages.append(messages)
        return AgentResponse(reply=f"resposta {len(captured_messages)}")

    monkeypatch.setattr(agent_channel, "run_agent_turn", _fake_run_agent_turn)
    monkeypatch.setattr(agent_channel, "send_text_message", lambda **kwargs: None)

    try:
        agent_channel.try_handle(
            db, _inbound_to_agent(instructor_phone, "quem tenho amanha?")
        )
        agent_channel.try_handle(
            db, _inbound_to_agent(instructor_phone, "e depois de amanha?")
        )

        assert captured_messages[0] == [
            {"role": "user", "content": "quem tenho amanha?"}
        ]
        assert captured_messages[1] == [
            {"role": "user", "content": "quem tenho amanha?"},
            {"role": "assistant", "content": "resposta 1"},
            {"role": "user", "content": "e depois de amanha?"},
        ]
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_agent_turn_history_is_windowed_by_assistant_settings(monkeypatch) -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    _make_operator_user(db, professional.id)

    for i in range(5):
        agent_channel._record_turn(db, professional.id, "user", f"msg {i}")

    monkeypatch.setattr(agent_channel, "get_assistant_settings", lambda db_arg, pid: type(
        "S", (), {"memory_window_messages": 2}
    )())

    try:
        history = agent_channel._load_history(db, professional.id)
        assert history == [{"role": "user", "content": "msg 3"}, {"role": "user", "content": "msg 4"}]
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_agent_turn_history_drops_stale_turns(monkeypatch) -> None:
    """Old turns must not reach the model: a days-old "amanhã, dia 9 de
    agosto" answer in context makes it resolve today's "e amanhã?" to that
    stale date instead of calling resolve_date_phrase."""
    db = SessionLocal()
    professional = _make_professional(db)
    _make_operator_user(db, professional.id)

    stale = datetime.now(TIMEZONE) - agent_channel.HISTORY_MAX_AGE - timedelta(hours=1)
    db.add(
        AgentChannelMessage(
            professional_id=professional.id,
            role="assistant",
            content="Amanha, dia 9 de agosto de 2026, nao ha horarios vagos.",
            created_at=stale,
        )
    )
    db.commit()
    agent_channel._record_turn(db, professional.id, "user", "e amanha?")

    try:
        history = agent_channel._load_history(db, professional.id)
        assert history == [{"role": "user", "content": "e amanha?"}]
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_deterministic_command_does_not_pollute_agent_history(monkeypatch) -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    _make_operator_user(db, professional.id)
    monkeypatch.setattr(agent_channel, "send_text_message", lambda **kwargs: None)

    try:
        agent_channel.try_handle(
            db, _inbound_to_agent(professional.assistant_phone, "hoje")
        )
        assert (
            db.query(AgentChannelMessage)
            .filter(AgentChannelMessage.professional_id == professional.id)
            .count()
            == 0
        )
    finally:
        _cleanup(db, professionals=[professional])
        db.close()
