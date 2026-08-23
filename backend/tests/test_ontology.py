"""Integration tests for Places, RecurringSlots, and Contact enrichment
(customer ontology roadmap)."""

from pathlib import Path
import sys
import uuid
from datetime import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import (
    Appointment,
    AppointmentParticipant,
    AppointmentTransition,
    Contact,
    EntityAlias,
    OperationalEvent,
    Place,
    Professional,
    RecurringSlot,
    RecurringSlotOccurrenceParticipant,
    RecurringSlotParticipant,
    User,
)

client = TestClient(app)


def _random_email() -> str:
    return f"test_{uuid.uuid4().hex[:10]}@agenda.ai"


def _random_phone() -> str:
    return f"+55119{uuid.uuid4().hex[:8]}"


def _login_new_tenant(db):
    professional = Professional(name="Tenant", assistant_phone=_random_phone())
    db.add(professional)
    db.commit()

    user = User(
        email=_random_email(),
        hashed_password=hash_password("correct-password"),
        role="professional",
        professional_id=professional.id,
    )
    db.add(user)
    db.commit()

    login_res = client.post("/api/auth/login", json={"email": user.email, "password": "correct-password"})
    assert login_res.status_code == 200
    return professional, user, login_res.cookies


def _cleanup(db, *, professionals, users):
    professional_ids = [p.id for p in professionals]
    if professional_ids:
        db.query(OperationalEvent).filter(
            OperationalEvent.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(AppointmentParticipant).filter(
            AppointmentParticipant.appointment_id.in_(
                db.query(Appointment.id).filter(
                    Appointment.professional_id.in_(professional_ids)
                )
            )
        ).delete(synchronize_session=False)
        db.query(EntityAlias).filter(
            EntityAlias.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(AppointmentTransition).filter(
            AppointmentTransition.appointment_id.in_(
                db.query(Appointment.id).filter(
                    Appointment.professional_id.in_(professional_ids)
                )
            )
        ).delete(synchronize_session=False)
        db.query(Appointment).filter(
            Appointment.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(RecurringSlotParticipant).filter(
            RecurringSlotParticipant.recurring_slot_id.in_(
                db.query(RecurringSlot.id).filter(RecurringSlot.professional_id.in_(professional_ids))
            )
        ).delete(synchronize_session=False)
        db.query(RecurringSlotOccurrenceParticipant).filter(
            RecurringSlotOccurrenceParticipant.professional_id.in_(professional_ids)
        ).delete(synchronize_session=False)
        db.query(RecurringSlot).filter(RecurringSlot.professional_id.in_(professional_ids)).delete(
            synchronize_session=False
        )
        db.query(Contact).filter(Contact.professional_id.in_(professional_ids)).delete(
            synchronize_session=False
        )
        db.query(Place).filter(Place.professional_id.in_(professional_ids)).delete(
            synchronize_session=False
        )
    user_ids = [u.id for u in users]
    if user_ids:
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    if professional_ids:
        db.query(Professional).filter(Professional.id.in_(professional_ids)).delete(
            synchronize_session=False
        )
    db.commit()


def test_place_crud_and_tenant_isolation() -> None:
    db = SessionLocal()
    pro_a, user_a, cookies_a = _login_new_tenant(db)
    pro_b, user_b, cookies_b = _login_new_tenant(db)
    try:
        create_res = client.post(
            "/api/places", json={"name": "Clube A", "city": "São Paulo"}, cookies=cookies_a
        )
        assert create_res.status_code == 201
        place_id = create_res.json()["id"]

        list_res = client.get("/api/places", cookies=cookies_a)
        assert any(p["id"] == place_id for p in list_res.json()["places"])

        cross_tenant_res = client.get(f"/api/places/{place_id}", cookies=cookies_b)
        assert cross_tenant_res.status_code == 404

        update_res = client.patch(
            f"/api/places/{place_id}", json={"city": "Campinas"}, cookies=cookies_a
        )
        assert update_res.status_code == 200
        assert update_res.json()["city"] == "Campinas"
    finally:
        _cleanup(db, professionals=[pro_a, pro_b], users=[user_a, user_b])
        db.close()


def test_delete_place_cascades_recurring_slots_and_clears_contact_home_place() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        place_res = client.post("/api/places", json={"name": "Clube"}, cookies=cookies)
        place_id = place_res.json()["id"]

        slot_res = client.post(
            "/api/recurring-slots",
            json={"place_id": place_id, "day_of_week": 3, "start_time": "08:00:00", "end_time": "09:00:00"},
            cookies=cookies,
        )
        slot_id = slot_res.json()["id"]

        contact = Contact(
            professional_id=professional.id,
            phone=_random_phone(),
            display_name="Aluno",
            normalized_name="aluno",
            home_place_id=uuid.UUID(place_id),
        )
        db.add(contact)
        db.commit()

        delete_res = client.delete(f"/api/places/{place_id}", cookies=cookies)
        assert delete_res.status_code == 204

        assert db.query(RecurringSlot).filter(RecurringSlot.id == uuid.UUID(slot_id)).first() is None
        db.refresh(contact)
        assert contact.home_place_id is None
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_delete_place_rejects_calendar_class_reference() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        place_res = client.post("/api/places", json={"name": "Clube"}, cookies=cookies)
        place_id = uuid.UUID(place_res.json()["id"])
        db.add(
            RecurringSlot(
                professional_id=professional.id,
                place_id=place_id,
                day_of_week=3,
                start_time=time(10, 0),
                end_time=time(11, 0),
                slot_kind="class",
                class_type="group",
                max_participants=4,
            )
        )
        db.commit()

        delete_res = client.delete(f"/api/places/{place_id}", cookies=cookies)

        assert delete_res.status_code == 409
        assert db.query(Place).filter(Place.id == place_id).first() is not None
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_recurring_slot_overlap_is_rejected() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        place_res = client.post("/api/places", json={"name": "Clube"}, cookies=cookies)
        place_id = place_res.json()["id"]

        first = client.post(
            "/api/recurring-slots",
            json={
                "place_id": place_id,
                "day_of_week": 1,
                "start_time": "08:00:00",
                "end_time": "09:00:00",
            },
            cookies=cookies,
        )
        assert first.status_code == 201

        overlapping = client.post(
            "/api/recurring-slots",
            json={
                "place_id": place_id,
                "day_of_week": 1,
                "start_time": "08:30:00",
                "end_time": "09:30:00",
            },
            cookies=cookies,
        )
        assert overlapping.status_code == 409

        non_overlapping = client.post(
            "/api/recurring-slots",
            json={
                "place_id": place_id,
                "day_of_week": 1,
                "start_time": "09:00:00",
                "end_time": "10:00:00",
            },
            cookies=cookies,
        )
        assert non_overlapping.status_code == 201
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_recurring_slot_rejects_end_time_not_after_start_time() -> None:
    """A slot with end_time <= start_time (e.g. a midnight-end 00:00 picked
    without meaning "end of day") silently drops out of every downstream
    interval computation (compute_free_ranges_by_place, capacity segments,
    waitlist matching) instead of erroring — reject it at creation instead."""
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        place_res = client.post("/api/places", json={"name": "Clube"}, cookies=cookies)
        place_id = place_res.json()["id"]

        inverted = client.post(
            "/api/recurring-slots",
            json={
                "place_id": place_id,
                "day_of_week": 1,
                "start_time": "08:00:00",
                "end_time": "00:00:00",
            },
            cookies=cookies,
        )
        assert inverted.status_code == 422

        equal = client.post(
            "/api/recurring-slots",
            json={
                "place_id": place_id,
                "day_of_week": 1,
                "start_time": "08:00:00",
                "end_time": "08:00:00",
            },
            cookies=cookies,
        )
        assert equal.status_code == 422

        bulk_inverted = client.post(
            "/api/recurring-slots/bulk",
            json={
                "place_id": place_id,
                "days_of_week": [1, 2],
                "start_time": "08:00:00",
                "end_time": "00:00:00",
            },
            cookies=cookies,
        )
        assert bulk_inverted.status_code == 422

        created = client.post(
            "/api/recurring-slots",
            json={
                "place_id": place_id,
                "day_of_week": 1,
                "start_time": "08:00:00",
                "end_time": "09:00:00",
            },
            cookies=cookies,
        )
        assert created.status_code == 201
        slot_id = created.json()["id"]

        update_inverted = client.patch(
            f"/api/recurring-slots/{slot_id}",
            json={"end_time": "07:00:00"},
            cookies=cookies,
        )
        assert update_inverted.status_code == 422
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_recurring_slot_bulk_create_is_atomic() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        place_res = client.post("/api/places", json={"name": "Clube"}, cookies=cookies)
        place_id = place_res.json()["id"]

        bulk = client.post(
            "/api/recurring-slots/bulk",
            json={
                "place_id": place_id,
                "days_of_week": [0, 2, 4],
                "start_time": "08:00:00",
                "end_time": "09:00:00",
            },
            cookies=cookies,
        )
        assert bulk.status_code == 201
        assert [slot["day_of_week"] for slot in bulk.json()] == [0, 2, 4]

        conflicting = client.post(
            "/api/recurring-slots/bulk",
            json={
                "place_id": place_id,
                "days_of_week": [1, 2, 3],
                "start_time": "08:30:00",
                "end_time": "09:30:00",
            },
            cookies=cookies,
        )
        assert conflicting.status_code == 409

        saved_days = {
            slot.day_of_week
            for slot in db.query(RecurringSlot)
            .filter(RecurringSlot.professional_id == professional.id)
            .all()
        }
        assert saved_days == {0, 2, 4}
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_dashboard_can_create_incomplete_group_with_one_to_four_contacts() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        place = Place(
            professional_id=professional.id,
            name="Clube",
            normalized_name="clube",
        )
        contacts = [
            Contact(
                professional_id=professional.id,
                phone=_random_phone(),
                display_name=f"Aluno {index}",
                normalized_name=f"aluno {index}",
            )
            for index in range(1, 3)
        ]
        db.add(place)
        db.add_all(contacts)
        db.commit()

        one_person_group = client.post(
            "/api/appointments",
            json={
                "contact_id": str(contacts[0].id),
                "contact_ids": [str(contacts[0].id)],
                "place_id": str(place.id),
                "service": "Grupo iniciante",
                "start_at": "2026-08-10T08:00:00-03:00",
                "end_at": "2026-08-10T09:00:00-03:00",
                "class_type": "group",
            },
            cookies=cookies,
        )
        assert one_person_group.status_code == 201
        assert one_person_group.json()["class_type"] == "group"
        assert len(one_person_group.json()["participants"]) == 1

        two_person_group = client.post(
            "/api/appointments",
            json={
                "contact_id": str(contacts[0].id),
                "contact_ids": [str(contact.id) for contact in contacts],
                "place_id": str(place.id),
                "service": "Grupo intermediário",
                "start_at": "2026-08-10T09:00:00-03:00",
                "end_at": "2026-08-10T10:00:00-03:00",
                "class_type": "group",
            },
            cookies=cookies,
        )
        assert two_person_group.status_code == 201
        assert two_person_group.json()["class_type"] == "group"
        assert len(two_person_group.json()["participants"]) == 2

        calendar = client.get(
            "/api/calendar?start_date=2026-08-10&end_date=2026-08-10",
            cookies=cookies,
        )
        assert calendar.status_code == 200
        assert [row["class_type"] for row in calendar.json()["appointments"]] == [
            "group",
            "group",
        ]
        assert [len(row["participants"]) for row in calendar.json()["appointments"]] == [1, 2]
        assert [row["max_participants"] for row in calendar.json()["appointments"]] == [4, 4]
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_dashboard_can_create_empty_recurring_group_slot() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        place_res = client.post("/api/places", json={"name": "Clube"}, cookies=cookies)
        assert place_res.status_code == 201

        created = client.post(
            "/api/recurring-slots",
            json={
                "place_id": place_res.json()["id"],
                "day_of_week": 1,
                "start_time": "18:00:00",
                "end_time": "19:00:00",
                "slot_kind": "class",
                "class_type": "group",
                "max_participants": 4,
                "label": "Turma das 18h",
            },
            cookies=cookies,
        )
        assert created.status_code == 201
        assert created.json()["class_type"] == "group"
        assert created.json()["participant_count"] == 0
        assert created.json()["max_participants"] == 4

        conflicting = client.post(
            "/api/recurring-slots",
            json={
                "place_id": place_res.json()["id"],
                "day_of_week": 1,
                "start_time": "18:30:00",
                "end_time": "19:30:00",
                "slot_kind": "class",
                "class_type": "group",
                "max_participants": 4,
            },
            cookies=cookies,
        )
        assert conflicting.status_code == 409
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_dashboard_promotes_appointment_to_group_without_recreating_it() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        place = Place(
            professional_id=professional.id,
            name="Clube",
            normalized_name="clube",
        )
        contact = Contact(
            professional_id=professional.id,
            phone=_random_phone(),
            display_name="Maria",
            normalized_name="maria",
        )
        db.add_all([place, contact])
        db.commit()

        created = client.post(
            "/api/appointments",
            json={
                "contact_id": str(contact.id),
                "place_id": str(place.id),
                "service": "Aula",
                "start_at": "2026-08-10T08:00:00-03:00",
                "end_at": "2026-08-10T09:00:00-03:00",
            },
            cookies=cookies,
        )
        assert created.status_code == 201

        promoted = client.patch(
            f"/api/appointments/{created.json()['id']}/format",
            json={"class_type": "group", "max_participants": 3},
            cookies=cookies,
        )
        assert promoted.status_code == 200
        assert promoted.json()["id"] == created.json()["id"]
        assert promoted.json()["class_type"] == "group"
        assert promoted.json()["max_participants"] == 3
        assert [participant["contact_id"] for participant in promoted.json()["participants"]] == [
            str(contact.id)
        ]

        event = (
            db.query(OperationalEvent)
            .filter(
                OperationalEvent.professional_id == professional.id,
                OperationalEvent.event_type == "schedule.appointment.updated",
            )
            .one()
        )
        assert event.before_state == {"class_type": "individual", "max_participants": 1}
        assert event.after_state == {"class_type": "group", "max_participants": 3}
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_dashboard_adds_sporadic_customer_to_one_group_occurrence() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        place = client.post("/api/places", json={"name": "Clube"}, cookies=cookies)
        assert place.status_code == 201
        contact = Contact(
            professional_id=professional.id,
            phone=_random_phone(),
            display_name="Visitante",
            normalized_name="visitante",
        )
        db.add(contact)
        db.commit()
        slot = client.post(
            "/api/recurring-slots",
            json={
                "place_id": place.json()["id"],
                "day_of_week": 0,
                "start_time": "18:00:00",
                "end_time": "19:00:00",
                "slot_kind": "class",
                "class_type": "group",
                "max_participants": 2,
                "valid_from": "2026-08-03",
            },
            cookies=cookies,
        )
        assert slot.status_code == 201
        slot_id = slot.json()["id"]

        add_guest = client.post(
            f"/api/recurring-slots/{slot_id}/occurrences/2026-08-10/participants",
            json={"contact_id": str(contact.id)},
            cookies=cookies,
        )
        assert add_guest.status_code == 201
        assert add_guest.json()["occurrence_date"] == "2026-08-10"

        occurrence = client.get(
            f"/api/recurring-slots/{slot_id}/occurrences/2026-08-10",
            cookies=cookies,
        )
        assert occurrence.status_code == 200
        assert occurrence.json()["participant_count"] == 1
        assert occurrence.json()["participants"] == [
            {
                "id": str(contact.id),
                "contact_id": str(contact.id),
                "contact_name": "Visitante",
                "enrollment_scope": "occurrence",
            }
        ]

        calendar = client.get(
            "/api/calendar?start_date=2026-08-03&end_date=2026-08-10",
            cookies=cookies,
        )
        assert calendar.status_code == 200
        occurrences = calendar.json()["recurring_classes"]
        assert [len(item["participants"]) for item in occurrences] == [0, 1]
        assert occurrences[1]["participants"][0]["display_name"] == "Visitante"

        remove_guest = client.delete(
            f"/api/recurring-slots/{slot_id}/occurrences/2026-08-10/participants/{contact.id}",
            cookies=cookies,
        )
        assert remove_guest.status_code == 204
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_dashboard_booking_uses_reserved_place_without_being_blocked() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    other_professional, other_user, other_cookies = _login_new_tenant(db)
    try:
        place_res = client.post("/api/places", json={"name": "Clube"}, cookies=cookies)
        place_id = place_res.json()["id"]

        contact = Contact(
            professional_id=professional.id,
            phone=_random_phone(),
            display_name="Aluno",
            normalized_name="aluno",
        )
        db.add(contact)
        db.commit()

        slot_res = client.post(
            "/api/recurring-slots",
            json={
                "place_id": place_id,
                "day_of_week": 0,
                "start_time": "08:00:00",
                "end_time": "10:00:00",
            },
            cookies=cookies,
        )
        assert slot_res.status_code == 201

        booking = client.post(
            "/api/appointments",
            json={
                "contact_id": str(contact.id),
                "place_id": place_id,
                "service": "Aula de tênis",
                "start_at": "2026-08-10T08:30:00-03:00",
                "end_at": "2026-08-10T09:30:00-03:00",
                "is_recurring": True,
            },
            cookies=cookies,
        )
        assert booking.status_code == 201
        assert booking.json()["place_id"] == place_id
        assert booking.json()["place_name"] == "Clube"
        assert booking.json()["status"] == "confirmed"
        assert booking.json()["source"] == "dashboard"
        assert booking.json()["recurrence_rule"] == "FREQ=WEEKLY"

        calendar = client.get(
            "/api/calendar?start_date=2026-08-10&end_date=2026-08-10",
            cookies=cookies,
        )
        assert calendar.status_code == 200
        calendar_booking = calendar.json()["appointments"][0]
        assert calendar_booking["place_id"] == place_id
        assert calendar_booking["place_name"] == "Clube"
        # /api/calendar now returns one row per dated occurrence (via the
        # same override-aware projection the instructor agent uses), so a
        # per-row recurrence_rule no longer applies — recurrence is proven
        # below instead, by the booking also appearing on the following
        # week's matching weekday.

        future_calendar = client.get(
            "/api/calendar?start_date=2026-08-17&end_date=2026-08-17",
            cookies=cookies,
        )
        assert future_calendar.status_code == 200
        assert len(future_calendar.json()["appointments"]) == 1

        overlapping_future_occurrence = client.post(
            "/api/appointments",
            json={
                "contact_id": str(contact.id),
                "place_id": place_id,
                "service": "Aula de tênis",
                "start_at": "2026-08-17T09:00:00-03:00",
                "end_at": "2026-08-17T10:00:00-03:00",
            },
            cookies=cookies,
        )
        assert overlapping_future_occurrence.status_code == 409

        overlapping = client.post(
            "/api/appointments",
            json={
                "contact_id": str(contact.id),
                "place_id": place_id,
                "service": "Aula de tênis",
                "start_at": "2026-08-10T09:00:00-03:00",
                "end_at": "2026-08-10T10:00:00-03:00",
            },
            cookies=cookies,
        )
        assert overlapping.status_code == 409

        transition = (
            db.query(AppointmentTransition)
            .filter(AppointmentTransition.appointment_id == uuid.UUID(booking.json()["id"]))
            .one()
        )
        assert transition.action == "create"
        assert transition.new_status == "confirmed"

        cross_tenant = client.post(
            "/api/appointments",
            json={
                "contact_id": str(contact.id),
                "place_id": place_id,
                "service": "Aula de tênis",
                "start_at": "2026-08-10T10:00:00-03:00",
                "end_at": "2026-08-10T11:00:00-03:00",
            },
            cookies=other_cookies,
        )
        assert cross_tenant.status_code == 404
    finally:
        _cleanup(
            db,
            professionals=[professional, other_professional],
            users=[user, other_user],
        )
        db.close()


def test_appointment_inherits_the_unique_covering_place_stay() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        place_res = client.post("/api/places", json={"name": "Clube"}, cookies=cookies)
        place_id = uuid.UUID(place_res.json()["id"])
        contact = Contact(
            professional_id=professional.id,
            phone=_random_phone(),
            display_name="Aluno",
            normalized_name="aluno",
        )
        stay = RecurringSlot(
            professional_id=professional.id,
            place_id=place_id,
            day_of_week=0,
            start_time=time(10, 0),
            end_time=time(12, 0),
            slot_kind="availability",
        )
        db.add_all([contact, stay])
        db.commit()

        appointment_res = client.post(
            "/api/appointments",
            json={
                "contact_id": str(contact.id),
                "service": "Aula",
                "start_at": "2026-08-03T10:00:00-03:00",
                "end_at": "2026-08-03T11:00:00-03:00",
            },
            cookies=cookies,
        )

        assert appointment_res.status_code == 201
        assert appointment_res.json()["place_id"] == str(place_id)

        moved_stay = client.patch(
            f"/api/recurring-slots/{stay.id}",
            json={"start_time": "12:00:00", "end_time": "14:00:00"},
            cookies=cookies,
        )
        assert moved_stay.status_code == 200
        persisted = client.get(
            f"/api/appointments/{appointment_res.json()['id']}", cookies=cookies
        )
        assert persisted.status_code == 200
        assert persisted.json()["place_id"] == str(place_id)
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_appointment_requires_explicit_place_outside_a_stay() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        place_res = client.post("/api/places", json={"name": "Clube"}, cookies=cookies)
        place_id = uuid.UUID(place_res.json()["id"])
        contact = Contact(
            professional_id=professional.id,
            phone=_random_phone(),
            display_name="Aluno",
            normalized_name="aluno",
        )
        db.add(contact)
        db.commit()

        body = {
            "contact_id": str(contact.id),
            "service": "Aula",
            "start_at": "2026-08-03T13:00:00-03:00",
            "end_at": "2026-08-03T14:00:00-03:00",
        }
        unresolved = client.post("/api/appointments", json=body, cookies=cookies)
        assert unresolved.status_code == 409

        explicit = client.post(
            "/api/appointments",
            json={**body, "place_id": str(place_id)},
            cookies=cookies,
        )
        assert explicit.status_code == 201
        transition = (
            db.query(AppointmentTransition)
            .filter(AppointmentTransition.appointment_id == uuid.UUID(explicit.json()["id"]))
            .one()
        )
        assert transition.metadata_["place_resolution"] == {
            "stay_id": None,
            "explicit_exception": True,
        }
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_recurring_slot_participant_capacity_enforced() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        place_res = client.post("/api/places", json={"name": "Clube"}, cookies=cookies)
        place_id = place_res.json()["id"]

        slot_res = client.post(
            "/api/recurring-slots",
            json={
                "place_id": place_id,
                "day_of_week": 2,
                "start_time": "10:00:00",
                "end_time": "11:00:00",
                "class_type": "group",
                "slot_kind": "class",
                "max_participants": 2,
            },
            cookies=cookies,
        )
        slot_id = slot_res.json()["id"]

        contacts = []
        for i in range(3):
            contact = Contact(
                professional_id=professional.id,
                phone=_random_phone(),
                display_name=f"Aluno {i}",
                normalized_name=f"aluno {i}",
            )
            db.add(contact)
            contacts.append(contact)
        db.commit()

        add_1 = client.post(
            f"/api/recurring-slots/{slot_id}/participants",
            json={"contact_id": str(contacts[0].id)},
            cookies=cookies,
        )
        assert add_1.status_code == 201

        add_2 = client.post(
            f"/api/recurring-slots/{slot_id}/participants",
            json={"contact_id": str(contacts[1].id)},
            cookies=cookies,
        )
        assert add_2.status_code == 201

        add_3_over_capacity = client.post(
            f"/api/recurring-slots/{slot_id}/participants",
            json={"contact_id": str(contacts[2].id)},
            cookies=cookies,
        )
        assert add_3_over_capacity.status_code == 409

        duplicate = client.post(
            f"/api/recurring-slots/{slot_id}/participants",
            json={"contact_id": str(contacts[0].id)},
            cookies=cookies,
        )
        assert duplicate.status_code == 409

        remove_res = client.delete(
            f"/api/recurring-slots/{slot_id}/participants/{contacts[0].id}", cookies=cookies
        )
        assert remove_res.status_code == 204

        contact_detail = client.get(f"/api/contacts/{contacts[1].id}", cookies=cookies)
        assert contact_detail.status_code == 200
        assert len(contact_detail.json()["fixed_slots"]) == 1
        assert contact_detail.json()["fixed_slots"][0]["id"] == slot_id
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_create_recurring_group_with_one_initial_contact() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        place_res = client.post("/api/places", json={"name": "Clube"}, cookies=cookies)
        place_id = place_res.json()["id"]
        contact = Contact(
            professional_id=professional.id,
            phone=_random_phone(),
            display_name="Aluno inicial",
            normalized_name="aluno inicial",
        )
        db.add(contact)
        db.commit()

        created = client.post(
            "/api/recurring-slots/groups",
            json={
                "place_id": place_id,
                "day_of_week": 1,
                "start_time": "18:00:00",
                "end_time": "19:00:00",
                "level": "beginner",
                "max_participants": 2,
                "contact_ids": [str(contact.id)],
            },
            cookies=cookies,
        )

        assert created.status_code == 201
        assert created.json()["participant_count"] == 1
        assert created.json()["max_participants"] == 2

        detail = client.get(
            f"/api/recurring-slots/{created.json()['id']}",
            cookies=cookies,
        )
        assert detail.status_code == 200
        assert [participant["contact_id"] for participant in detail.json()["participants"]] == [
            str(contact.id)
        ]
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_add_participant_rejects_cross_tenant_contact() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    other_professional, other_user, _ = _login_new_tenant(db)
    try:
        place_res = client.post("/api/places", json={"name": "Clube"}, cookies=cookies)
        slot_res = client.post(
            "/api/recurring-slots",
            json={
                "place_id": place_res.json()["id"],
                "day_of_week": 2,
                "start_time": "10:00:00",
                    "end_time": "11:00:00",
                    "class_type": "group",
                    "slot_kind": "class",
                    "max_participants": 2,
            },
            cookies=cookies,
        )
        other_contact = Contact(
            professional_id=other_professional.id,
            phone=_random_phone(),
            display_name="Cliente de outro tenant",
            normalized_name="cliente de outro tenant",
        )
        db.add(other_contact)
        db.commit()

        response = client.post(
            f"/api/recurring-slots/{slot_res.json()['id']}/participants",
            json={"contact_id": str(other_contact.id)},
            cookies=cookies,
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Contact not found"
    finally:
        _cleanup(
            db,
            professionals=[professional, other_professional],
            users=[user, other_user],
        )
        db.close()


def test_create_recurring_group_assigns_selected_contacts_atomically() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    other_professional, other_user, other_cookies = _login_new_tenant(db)
    try:
        place_res = client.post("/api/places", json={"name": "Clube"}, cookies=cookies)
        place_id = place_res.json()["id"]

        contacts = [
            Contact(
                professional_id=professional.id,
                phone=_random_phone(),
                display_name=f"Aluno {index}",
                normalized_name=f"aluno {index}",
            )
            for index in range(2)
        ]
        other_contact = Contact(
            professional_id=other_professional.id,
            phone=_random_phone(),
            display_name="Outro tenant",
            normalized_name="outro tenant",
        )
        db.add_all([*contacts, other_contact])
        db.commit()

        reserved_place_slot = client.post(
            "/api/recurring-slots",
            json={
                "place_id": place_id,
                "day_of_week": 1,
                "start_time": "17:00:00",
                "end_time": "20:00:00",
            },
            cookies=cookies,
        )
        assert reserved_place_slot.status_code == 201

        created = client.post(
            "/api/recurring-slots/groups",
            json={
                "place_id": place_id,
                "day_of_week": 1,
                "start_time": "18:00:00",
                "end_time": "19:00:00",
                "label": "Turma noite",
                "level": "intermediate",
                "max_participants": 3,
                "contact_ids": [str(contact.id) for contact in contacts],
            },
            cookies=cookies,
        )
        assert created.status_code == 201
        assert created.json()["class_type"] == "group"
        assert created.json()["participant_count"] == 2
        assert created.json()["max_participants"] == 3
        assert created.json()["level"] == "intermediate"
        assert created.json()["recurrence_type"] == "weekly"

        group_detail = client.get(
            f"/api/recurring-slots/{created.json()['id']}",
            cookies=cookies,
        )
        assert group_detail.status_code == 200
        assert [participant["contact_name"] for participant in group_detail.json()["participants"]] == [
            "Aluno 0",
            "Aluno 1",
        ]

        hidden_from_other_tenant = client.get(
            f"/api/recurring-slots/{created.json()['id']}",
            cookies=other_cookies,
        )
        assert hidden_from_other_tenant.status_code == 404

        blocked_booking = client.post(
            "/api/appointments",
            json={
                "contact_id": str(contacts[0].id),
                "place_id": place_id,
                "service": "Aula de tênis",
                "start_at": "2026-08-11T18:30:00-03:00",
                "end_at": "2026-08-11T19:00:00-03:00",
            },
            cookies=cookies,
        )
        assert blocked_booking.status_code == 409

        sporadic = client.post(
            "/api/recurring-slots/groups",
            json={
                "place_id": place_id,
                "day_of_week": 3,
                "start_time": "20:00:00",
                "end_time": "21:00:00",
                "level": "advanced",
                "max_participants": 2,
                "contact_ids": [str(contact.id) for contact in contacts],
                "recurrence_type": "once",
                "scheduled_date": "2026-08-06",
            },
            cookies=cookies,
        )
        assert sporadic.status_code == 201
        assert sporadic.json()["recurrence_type"] == "once"
        assert sporadic.json()["scheduled_date"] == "2026-08-06"

        slot_count_before = (
            db.query(RecurringSlot)
            .filter(RecurringSlot.professional_id == professional.id)
            .count()
        )
        cross_tenant = client.post(
            "/api/recurring-slots/groups",
            json={
                "place_id": place_id,
                "day_of_week": 2,
                "start_time": "18:00:00",
                "end_time": "19:00:00",
                "level": "beginner",
                "max_participants": 2,
                "contact_ids": [str(contacts[0].id), str(other_contact.id)],
            },
            cookies=cookies,
        )
        assert cross_tenant.status_code == 404
        assert (
            db.query(RecurringSlot)
            .filter(RecurringSlot.professional_id == professional.id)
            .count()
            == slot_count_before
        )
    finally:
        _cleanup(
            db,
            professionals=[professional, other_professional],
            users=[user, other_user],
        )
        db.close()


def test_contact_update_and_tenant_isolation() -> None:
    db = SessionLocal()
    pro_a, user_a, cookies_a = _login_new_tenant(db)
    pro_b, user_b, cookies_b = _login_new_tenant(db)
    try:
        contact = Contact(
            professional_id=pro_a.id,
            phone=_random_phone(),
            display_name="Aluno Teste",
            normalized_name="aluno teste",
        )
        db.add(contact)
        db.commit()

        update_res = client.patch(
            f"/api/contacts/{contact.id}",
            json={"level": "intermediate", "city": "São Paulo"},
            cookies=cookies_a,
        )
        assert update_res.status_code == 200
        assert update_res.json()["level"] == "intermediate"

        cross_tenant_res = client.get(f"/api/contacts/{contact.id}", cookies=cookies_b)
        assert cross_tenant_res.status_code == 404

        list_res = client.get("/api/contacts", cookies=cookies_a)
        assert any(c["id"] == str(contact.id) for c in list_res.json()["contacts"])
    finally:
        _cleanup(db, professionals=[pro_a, pro_b], users=[user_a, user_b])
        db.close()


def test_place_create_and_update_set_normalized_name() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        create_res = client.post(
            "/api/places", json={"name": "  Clube Harmonia  "}, cookies=cookies
        )
        assert create_res.status_code == 201
        place_id = create_res.json()["id"]
        stored = db.query(Place).filter(Place.id == place_id).one()
        assert stored.normalized_name == "clube harmonia"

        update_res = client.patch(
            f"/api/places/{place_id}",
            json={"name": "Clube Harmonia II"},
            cookies=cookies,
        )
        assert update_res.status_code == 200
        db.refresh(stored)
        assert stored.normalized_name == "clube harmonia ii"
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_recurring_slot_availability_rejects_participant_assignment() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        place_res = client.post("/api/places", json={"name": "Clube"}, cookies=cookies)
        place_id = place_res.json()["id"]

        slot_res = client.post(
            "/api/recurring-slots",
            json={
                "place_id": place_id,
                "day_of_week": 3,
                "start_time": "10:00:00",
                "end_time": "11:00:00",
            },
            cookies=cookies,
        )
        assert slot_res.status_code == 201
        slot_id = slot_res.json()["id"]
        assert slot_res.json()["slot_kind"] == "availability"

        class_list_res = client.get(
            "/api/recurring-slots?slot_kind=class", cookies=cookies
        )
        assert class_list_res.status_code == 200
        assert class_list_res.json()["slots"] == []

        transition_res = client.patch(
            f"/api/recurring-slots/{slot_id}",
            json={"slot_kind": "class"},
            cookies=cookies,
        )
        assert transition_res.status_code == 422

        contact = Contact(
            professional_id=professional.id,
            phone=_random_phone(),
            display_name="Aluno",
            normalized_name="aluno",
        )
        db.add(contact)
        db.commit()

        add_res = client.post(
            f"/api/recurring-slots/{slot_id}/participants",
            json={"contact_id": str(contact.id)},
            cookies=cookies,
        )
        assert add_res.status_code == 409

        slot = db.query(RecurringSlot).filter(RecurringSlot.id == slot_id).one()
        assert slot.slot_kind == "availability"
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_recurring_slot_availability_rejects_class_fields() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        place_res = client.post("/api/places", json={"name": "Clube"}, cookies=cookies)
        place_id = place_res.json()["id"]

        slot_res = client.post(
            "/api/recurring-slots",
            json={
                "place_id": place_id,
                "day_of_week": 3,
                "start_time": "10:00:00",
                "end_time": "11:00:00",
                "slot_kind": "availability",
                "class_type": "group",
                "max_participants": 4,
            },
            cookies=cookies,
        )

        assert slot_res.status_code == 422
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_recurring_slot_database_constraint_keeps_availability_neutral() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        place_res = client.post("/api/places", json={"name": "Clube"}, cookies=cookies)
        place_id = uuid.UUID(place_res.json()["id"])
        invalid_slot = RecurringSlot(
            professional_id=professional.id,
            place_id=place_id,
            day_of_week=3,
            start_time=time(10, 0),
            end_time=time(11, 0),
            slot_kind="availability",
            class_type="group",
            max_participants=4,
        )
        db.add(invalid_slot)

        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_create_recurring_group_sets_slot_kind_class_and_group_name() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        place_res = client.post("/api/places", json={"name": "Clube"}, cookies=cookies)
        place_id = place_res.json()["id"]

        contact = Contact(
            professional_id=professional.id,
            phone=_random_phone(),
            display_name="Maria",
            normalized_name="maria",
        )
        db.add(contact)
        db.commit()

        group_res = client.post(
            "/api/recurring-slots/groups",
            json={
                "place_id": place_id,
                "day_of_week": 4,
                "start_time": "18:00:00",
                "end_time": "19:00:00",
                "group_name": "Grupo da Maria",
                "level": "beginner",
                "max_participants": 4,
                "contact_ids": [str(contact.id)],
            },
            cookies=cookies,
        )
        assert group_res.status_code == 201
        body = group_res.json()
        assert body["slot_kind"] == "class"
        assert body["group_name"] == "Grupo da Maria"
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()


def test_entity_alias_normalized_alias_unique_per_tenant_and_type() -> None:
    db = SessionLocal()
    professional, user, cookies = _login_new_tenant(db)
    try:
        place_res = client.post("/api/places", json={"name": "Clube Harmonia"}, cookies=cookies)
        place_id = place_res.json()["id"]

        alias = EntityAlias(
            professional_id=professional.id,
            entity_type="place",
            entity_id=uuid.UUID(place_id),
            alias="Harmonia",
            normalized_alias="harmonia",
        )
        db.add(alias)
        db.commit()

        duplicate = EntityAlias(
            professional_id=professional.id,
            entity_type="place",
            entity_id=uuid.UUID(place_id),
            alias="HARMONIA",
            normalized_alias="harmonia",
        )
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        _cleanup(db, professionals=[professional], users=[user])
        db.close()
