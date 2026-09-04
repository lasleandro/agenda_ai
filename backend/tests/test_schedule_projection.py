"""Tests for the shared schedule occurrence projection service
(operational ontology roadmap v0.2, Phase 1)."""

from pathlib import Path
import sys
import uuid
from datetime import date, datetime, time, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import (
    Appointment,
    Contact,
    Place,
    Professional,
    RecurringSlot,
    RecurringSlotOccurrenceParticipant,
    RecurringSlotParticipant,
    ScheduleOccurrenceOverride,
    ScheduleOccurrenceClassOverride,
)
from app.services.scheduling import TIMEZONE, list_schedule_occurrences

MONDAY = date(2026, 8, 3)  # a known Monday


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().int % 100_000_000:08d}"


def _make_professional(db) -> Professional:
    professional = Professional(name="Tenant Schedule", assistant_phone=_random_phone())
    db.add(professional)
    db.commit()
    return professional


def _make_contact(db, professional_id) -> Contact:
    contact = Contact(
        professional_id=professional_id,
        phone=_random_phone(),
        display_name="Aluno",
        normalized_name="aluno",
    )
    db.add(contact)
    db.commit()
    return contact


def _make_place(db, professional_id) -> Place:
    place = Place(professional_id=professional_id, name="Clube", normalized_name="clube")
    db.add(place)
    db.commit()
    return place


def _cleanup(db, *, professionals: list[Professional]) -> None:
    professional_ids = [p.id for p in professionals]
    if not professional_ids:
        return
    db.query(ScheduleOccurrenceOverride).filter(
        ScheduleOccurrenceOverride.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(ScheduleOccurrenceClassOverride).filter(
        ScheduleOccurrenceClassOverride.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(RecurringSlotParticipant).filter(
        RecurringSlotParticipant.recurring_slot_id.in_(
            db.query(RecurringSlot.id).filter(
                RecurringSlot.professional_id.in_(professional_ids)
            )
        )
    ).delete(synchronize_session=False)
    db.query(RecurringSlotOccurrenceParticipant).filter(
        RecurringSlotOccurrenceParticipant.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(RecurringSlot).filter(
        RecurringSlot.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(Appointment).filter(
        Appointment.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(Contact).filter(Contact.professional_id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.query(Place).filter(Place.professional_id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.query(Professional).filter(Professional.id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.commit()


def test_weekly_appointment_expands_across_recurrence_boundary() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        contact = _make_contact(db, professional.id)
        start_at = datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE)
        appointment = Appointment(
            professional_id=professional.id,
            contact_id=contact.id,
            service="Aula individual",
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
            recurrence_rule="FREQ=WEEKLY",
        )
        db.add(appointment)
        db.commit()

        occurrences = list_schedule_occurrences(
            db, professional.id, MONDAY, MONDAY + timedelta(days=21)
        )
        assert [o.occurrence_date for o in occurrences] == [
            MONDAY,
            MONDAY + timedelta(days=7),
            MONDAY + timedelta(days=14),
            MONDAY + timedelta(days=21),
        ]
        assert all(o.starts_at.time() == time(10, 0) for o in occurrences)
        assert all(o.source_type == "appointment" for o in occurrences)
        assert all(not o.is_exception for o in occurrences)
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_recurring_class_slot_expands_and_excludes_availability_only_slots() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        place = _make_place(db, professional.id)
        contact = _make_contact(db, professional.id)
        created_at = datetime.combine(MONDAY, time(8, 0), tzinfo=TIMEZONE)

        class_slot = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=0,
            start_time=time(18, 0),
            end_time=time(19, 0),
            class_type="group",
            slot_kind="class",
            max_participants=4,
            recurrence_type="weekly",
            created_at=created_at,
            valid_from=MONDAY + timedelta(days=7),
            valid_until=MONDAY + timedelta(days=14),
        )
        availability_slot = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=0,
            start_time=time(7, 0),
            end_time=time(8, 0),
            recurrence_type="weekly",
            created_at=created_at,
        )
        db.add_all([class_slot, availability_slot])
        db.flush()
        db.add(
            RecurringSlotParticipant(recurring_slot_id=class_slot.id, contact_id=contact.id)
        )
        db.commit()

        occurrences = list_schedule_occurrences(
            db, professional.id, MONDAY, MONDAY + timedelta(days=21)
        )
        assert [occurrence.occurrence_date for occurrence in occurrences] == [
            MONDAY + timedelta(days=7),
            MONDAY + timedelta(days=14),
        ]
        assert all(o.source_type == "recurring_slot" for o in occurrences)
        assert all(o.source_id == class_slot.id for o in occurrences)
        assert all(o.status == "scheduled" for o in occurrences)
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_empty_recurring_group_projects_as_busy_group_occurrences() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        place = _make_place(db, professional.id)
        slot = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=MONDAY.weekday(),
            start_time=time(18, 0),
            end_time=time(19, 0),
            class_type="group",
            slot_kind="class",
            max_participants=4,
            recurrence_type="weekly",
            created_at=datetime.combine(MONDAY, time(8, 0), tzinfo=TIMEZONE),
        )
        db.add(slot)
        db.commit()

        occurrences = list_schedule_occurrences(db, professional.id, MONDAY, MONDAY)

        assert len(occurrences) == 1
        assert occurrences[0].source_id == slot.id
        assert occurrences[0].class_type == "group"
        assert occurrences[0].max_participants == 4
        assert occurrences[0].participants == []
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_recurring_group_occurrence_includes_dated_guest_only_on_that_date() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        place = _make_place(db, professional.id)
        permanent = _make_contact(db, professional.id)
        guest = _make_contact(db, professional.id)
        guest.display_name = "Convidada"
        slot = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=MONDAY.weekday(),
            start_time=time(18, 0),
            end_time=time(19, 0),
            class_type="group",
            slot_kind="class",
            max_participants=3,
            recurrence_type="weekly",
            created_at=datetime.combine(MONDAY, time(8, 0), tzinfo=TIMEZONE),
        )
        db.add(slot)
        db.flush()
        db.add(RecurringSlotParticipant(recurring_slot_id=slot.id, contact_id=permanent.id))
        db.add(
            RecurringSlotOccurrenceParticipant(
                professional_id=professional.id,
                recurring_slot_id=slot.id,
                contact_id=guest.id,
                occurrence_date=MONDAY + timedelta(days=7),
            )
        )
        db.commit()

        occurrences = list_schedule_occurrences(
            db, professional.id, MONDAY, MONDAY + timedelta(days=7)
        )

        assert [
            [participant.contact_name for participant in occurrence.participants]
            for occurrence in occurrences
        ] == [["Aluno"], ["Aluno", "Convidada"]]
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_occurrence_class_override_changes_only_selected_recurring_class() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        place = _make_place(db, professional.id)
        slot = RecurringSlot(
            professional_id=professional.id,
            place_id=place.id,
            day_of_week=MONDAY.weekday(),
            start_time=time(18, 0),
            end_time=time(19, 0),
            class_type="individual",
            slot_kind="class",
            max_participants=1,
            recurrence_type="weekly",
            valid_from=MONDAY,
        )
        db.add(slot)
        db.flush()
        db.add(
            ScheduleOccurrenceClassOverride(
                professional_id=professional.id,
                recurring_slot_id=slot.id,
                occurrence_date=MONDAY + timedelta(days=7),
                class_type="group",
                max_participants=3,
            )
        )
        db.commit()

        occurrences = list_schedule_occurrences(
            db, professional.id, MONDAY, MONDAY + timedelta(days=7)
        )

        assert [(item.class_type, item.max_participants) for item in occurrences] == [
            ("individual", 1),
            ("group", 3),
        ]
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_cancelled_override_removes_the_occurrence() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        contact = _make_contact(db, professional.id)
        start_at = datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE)
        appointment = Appointment(
            professional_id=professional.id,
            contact_id=contact.id,
            service="Aula individual",
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
            recurrence_rule="FREQ=WEEKLY",
        )
        db.add(appointment)
        db.flush()
        cancelled_date = MONDAY + timedelta(days=7)
        db.add(
            ScheduleOccurrenceOverride(
                professional_id=professional.id,
                appointment_id=appointment.id,
                occurrence_date=cancelled_date,
                override_type="cancelled",
            )
        )
        db.commit()

        occurrences = list_schedule_occurrences(
            db, professional.id, MONDAY, MONDAY + timedelta(days=14)
        )
        assert cancelled_date not in [o.occurrence_date for o in occurrences]
        assert len(occurrences) == 2
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_rescheduled_override_moves_occurrence_and_flags_exception() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        place = _make_place(db, professional.id)
        contact = _make_contact(db, professional.id)
        start_at = datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE)
        appointment = Appointment(
            professional_id=professional.id,
            contact_id=contact.id,
            place_id=place.id,
            service="Aula individual",
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
            recurrence_rule="FREQ=WEEKLY",
        )
        db.add(appointment)
        db.flush()
        original_date = MONDAY + timedelta(days=7)
        new_start = datetime.combine(
            original_date + timedelta(days=1), time(14, 0), tzinfo=TIMEZONE
        )
        db.add(
            ScheduleOccurrenceOverride(
                professional_id=professional.id,
                appointment_id=appointment.id,
                occurrence_date=original_date,
                override_type="rescheduled",
                replacement_start_at=new_start,
                replacement_end_at=new_start + timedelta(hours=1),
            )
        )
        db.commit()

        occurrences = list_schedule_occurrences(
            db, professional.id, MONDAY, MONDAY + timedelta(days=14)
        )
        assert len(occurrences) == 3
        assert original_date not in [
            o.occurrence_date for o in occurrences if not o.is_exception
        ]
        moved = next(o for o in occurrences if o.is_exception)
        assert moved.occurrence_date == original_date + timedelta(days=1)
        assert moved.starts_at == new_start
        assert moved.place_id == place.id
    finally:
        _cleanup(db, professionals=[professional])
        db.close()


def test_override_is_scoped_to_owning_professional() -> None:
    db = SessionLocal()
    professional_a = _make_professional(db)
    professional_b = _make_professional(db)
    try:
        contact_a = _make_contact(db, professional_a.id)
        contact_b = _make_contact(db, professional_b.id)
        start_at = datetime.combine(MONDAY, time(10, 0), tzinfo=TIMEZONE)

        appointment_a = Appointment(
            professional_id=professional_a.id,
            contact_id=contact_a.id,
            service="Aula A",
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
            recurrence_rule="FREQ=WEEKLY",
        )
        appointment_b = Appointment(
            professional_id=professional_b.id,
            contact_id=contact_b.id,
            service="Aula B",
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status="confirmed",
            source="dashboard",
            recurrence_rule="FREQ=WEEKLY",
        )
        db.add_all([appointment_a, appointment_b])
        db.flush()
        target_date = MONDAY + timedelta(days=7)
        db.add(
            ScheduleOccurrenceOverride(
                professional_id=professional_a.id,
                appointment_id=appointment_a.id,
                occurrence_date=target_date,
                override_type="cancelled",
            )
        )
        db.commit()

        occurrences_a = list_schedule_occurrences(
            db, professional_a.id, MONDAY, MONDAY + timedelta(days=14)
        )
        occurrences_b = list_schedule_occurrences(
            db, professional_b.id, MONDAY, MONDAY + timedelta(days=14)
        )
        assert len(occurrences_a) == 2
        assert len(occurrences_b) == 3
        assert target_date in [o.occurrence_date for o in occurrences_b]
    finally:
        _cleanup(db, professionals=[professional_a, professional_b])
        db.close()


def test_occurrence_date_bucketed_by_local_timezone_not_utc() -> None:
    db = SessionLocal()
    professional = _make_professional(db)
    try:
        contact = _make_contact(db, professional.id)
        # 23:30 local time — 02:30 UTC the *next* calendar day, since
        # America/Sao_Paulo is UTC-3. The occurrence must bucket to the
        # local date, not the UTC date.
        local_start = datetime.combine(MONDAY, time(23, 30), tzinfo=TIMEZONE)
        appointment = Appointment(
            professional_id=professional.id,
            contact_id=contact.id,
            service="Aula noturna",
            start_at=local_start,
            end_at=local_start + timedelta(minutes=30),
            status="confirmed",
            source="dashboard",
        )
        db.add(appointment)
        db.commit()

        occurrences = list_schedule_occurrences(db, professional.id, MONDAY, MONDAY)
        assert len(occurrences) == 1
        assert occurrences[0].occurrence_date == MONDAY
    finally:
        _cleanup(db, professionals=[professional])
        db.close()
