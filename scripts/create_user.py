"""Manual user provisioning through verified email activation.

Usage:
    cd backend
    python ../scripts/create_user.py --email admin@agenda.ai --role platform_admin
    python ../scripts/create_user.py --email joao@agenda.ai --role professional \
        --professional-id a0000000-0000-0000-0000-000000000001
"""

import argparse
import os
import sys
import uuid

_backend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.database import SessionLocal  # noqa: E402
from app.models import Professional, User  # noqa: E402
from app.models.auth_action_token import ACCOUNT_ACTIVATION  # noqa: E402
from app.services.auth_emails import enqueue_auth_email  # noqa: E402
from app.services.auth_security import record_auth_event  # noqa: E402
from app.services.email_identity import normalize_email  # noqa: E402


def create_user(email: str, role: str, professional_id: uuid.UUID | None) -> User:
    """Create a pending user and queue its passwordless activation email."""
    if role == "platform_admin" and professional_id is not None:
        raise ValueError("platform_admin users must not have a professional_id")
    if role == "professional" and professional_id is None:
        raise ValueError("professional users require --professional-id")

    canonical_email = normalize_email(email)
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == canonical_email).first() is not None:
            raise ValueError("User already exists; use the resend flow if activation is pending")
        if professional_id is not None and db.get(Professional, professional_id) is None:
            raise ValueError(f"No Professional found with id {professional_id}")

        user = User(
            email=canonical_email,
            role=role,
            professional_id=professional_id,
            status="pending_activation",
        )
        db.add(user)
        db.flush()
        enqueue_auth_email(db, user=user, purpose=ACCOUNT_ACTIVATION)
        record_auth_event(
            db,
            event_type="account_activation_queued",
            user_id=user.id,
            email=user.email,
        )
        db.commit()
        return user
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", required=True, choices=["platform_admin", "professional"])
    parser.add_argument("--professional-id", type=uuid.UUID, default=None)
    args = parser.parse_args()
    create_user(args.email, args.role, args.professional_id)
    print(f"Created pending activation user: {args.email} (role={args.role})")
