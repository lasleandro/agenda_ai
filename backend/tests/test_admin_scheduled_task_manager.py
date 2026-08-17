"""Integration tests for platform-admin task manager queries."""

from datetime import date, datetime, time, timezone
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import OperationalEvent, Professional, ScheduledTask, ScheduledTaskRun, User
from app.models.scheduled_task import DAILY_AGENDA_SUMMARY

client = TestClient(app)


def _user(role: str, professional_id: uuid.UUID | None = None) -> User:
    return User(
        email=f"{uuid.uuid4().hex}@example.test",
        hashed_password=hash_password("correct-password"),
        role=role,
        professional_id=professional_id,
    )


def _professional(name: str) -> Professional:
    token = uuid.uuid4().hex[:8]
    return Professional(
        name=name,
        timezone="America/Sao_Paulo",
        agent_phone=f"+55119888{token}",
        assistant_phone=f"+55119777{token}",
    )


def _cleanup(db, professionals: list[Professional], users: list[User]) -> None:
    professional_ids = [professional.id for professional in professionals]
    task_ids = [
        task_id
        for (task_id,) in db.query(ScheduledTask.id)
        .filter(ScheduledTask.professional_id.in_(professional_ids))
        .all()
    ]
    if task_ids:
        db.query(ScheduledTaskRun).filter(
            ScheduledTaskRun.scheduled_task_id.in_(task_ids)
        ).delete(synchronize_session=False)
    db.query(ScheduledTask).filter(ScheduledTask.professional_id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.query(OperationalEvent).filter(
        OperationalEvent.professional_id.in_(professional_ids)
    ).delete(synchronize_session=False)
    db.query(User).filter(User.id.in_([user.id for user in users])).delete(
        synchronize_session=False
    )
    db.query(Professional).filter(Professional.id.in_(professional_ids)).delete(
        synchronize_session=False
    )
    db.commit()


def test_platform_admin_task_manager_searches_and_filters_without_exposing_run_body() -> None:
    db = SessionLocal()
    alpha = _professional("Alpha Task Tenant")
    beta = _professional("Beta Task Tenant")
    db.add_all([alpha, beta])
    db.flush()
    alpha_task = ScheduledTask(
        professional_id=alpha.id,
        task_type=DAILY_AGENDA_SUMMARY,
        enabled=True,
        local_time=time(7, 0),
    )
    beta_task = ScheduledTask(
        professional_id=beta.id,
        task_type=DAILY_AGENDA_SUMMARY,
        enabled=False,
        local_time=time(8, 0),
    )
    db.add_all([alpha_task, beta_task])
    db.flush()
    db.add_all(
        [
            ScheduledTaskRun(
                professional_id=alpha.id,
                scheduled_task_id=alpha_task.id,
                target_local_date=date(2026, 8, 17),
                scheduled_for_at=datetime(2026, 8, 17, 10, tzinfo=timezone.utc),
                status="delivered",
                attempt_count=1,
                rendered_body="Customer names must not be returned by the log.",
                provider_key="ycloud",
            ),
            ScheduledTaskRun(
                professional_id=beta.id,
                scheduled_task_id=beta_task.id,
                target_local_date=date(2026, 8, 18),
                scheduled_for_at=datetime(2026, 8, 18, 11, tzinfo=timezone.utc),
                status="failed",
                attempt_count=3,
                rendered_body="Private agenda body",
                provider_key="ycloud",
                last_error_code="provider_permanent",
                last_error_detail="Template rejected",
            ),
        ]
    )
    admin = _user("platform_admin")
    owner = _user("professional", alpha.id)
    db.add_all([admin, owner])
    db.commit()

    try:
        admin_login = client.post(
            "/api/auth/login", json={"email": admin.email, "password": "correct-password"}
        )
        suggestions = client.get(
            "/api/admin/scheduled-task-tenants?q=alpha", cookies=admin_login.cookies
        )
        assert suggestions.status_code == 200
        assert [row["id"] for row in suggestions.json()["tenants"]] == [str(alpha.id)]
        assert suggestions.json()["tenants"][0]["task_configured"] is True
        assert suggestions.json()["tenants"][0]["readiness_issues"] == []

        tasks = client.get(
            "/api/admin/scheduled-tasks?q=beta&enabled=false&page=1&page_size=1",
            cookies=admin_login.cookies,
        )
        assert tasks.status_code == 200
        assert tasks.json()["total"] == 1
        assert tasks.json()["page_size"] == 1
        assert tasks.json()["tasks"][0]["professional_id"] == str(beta.id)

        logs = client.get(
            "/api/admin/scheduled-task-runs?status=failed&has_error=true",
            cookies=admin_login.cookies,
        )
        assert logs.status_code == 200
        assert logs.json()["total"] == 1
        row = logs.json()["runs"][0]
        assert row["professional_id"] == str(beta.id)
        assert row["last_error_code"] == "provider_permanent"
        assert "rendered_body" not in row

        owner_login = client.post(
            "/api/auth/login", json={"email": owner.email, "password": "correct-password"}
        )
        assert client.get(
            "/api/admin/scheduled-task-runs", cookies=owner_login.cookies
        ).status_code == 403
    finally:
        _cleanup(db, [alpha, beta], [admin, owner])
        db.close()
