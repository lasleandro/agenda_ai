"""
Manual user onboarding (multi-tenancy roadmap Phase B/D — self-service
onboarding is a future phase; for now accounts are provisioned by hand).

Usage:
    cd backend
    python ../scripts/create_user.py --email admin@agenda.ai --password *** --role platform_admin
    python ../scripts/create_user.py --email joao@agenda.ai --password *** --role professional \
        --professional-id a0000000-0000-0000-0000-000000000001
"""

import argparse
import sys
import os
import uuid

_backend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.core.security import hash_password  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Professional, User  # noqa: E402


def create_user(email: str, password: str, role: str, professional_id: uuid.UUID | None) -> None:
    if role == "platform_admin" and professional_id is not None:
        raise ValueError("platform_admin users must not have a professional_id")
    if role == "professional" and professional_id is None:
        raise ValueError("professional users require --professional-id")

    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == email).first() is not None:
            print(f"User already exists: {email}")
            return

        if professional_id is not None and db.get(Professional, professional_id) is None:
            raise ValueError(f"No Professional found with id {professional_id}")

        user = User(
            email=email,
            hashed_password=hash_password(password),
            role=role,
            professional_id=professional_id,
        )
        db.add(user)
        db.commit()
        print(f"Created user: {email} (role={role})")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--role", required=True, choices=["platform_admin", "professional"])
    parser.add_argument("--professional-id", type=uuid.UUID, default=None)
    args = parser.parse_args()

    create_user(args.email, args.password, args.role, args.professional_id)
