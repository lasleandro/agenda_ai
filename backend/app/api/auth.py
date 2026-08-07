"""
Auth routes — real users, tenant-scoped JWT cookie session (multi-tenancy
roadmap Phases B and D).

POST /api/auth/login       — validate credentials against the users table,
                              set an httpOnly JWT cookie carrying role +
                              professional_id.
POST /api/auth/logout      — clear the cookie.
GET  /api/auth/me          — return the current session's identity + tenant.
POST /api/auth/impersonate — platform_admin only: swap the session into a
                              chosen tenant (professional_id), audit-logged.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import require_authenticated, require_platform_admin
from app.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    SESSION_COOKIE_NAME,
    create_access_token,
    verify_password,
)
from app.database import SessionLocal
from app.models import ImpersonationLog, Professional, User
from app.services.tenant_features import COMMERCIAL_FINANCIALS, is_tenant_feature_enabled

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class LoginRequest(BaseModel):
    email: str
    password: str


class ImpersonateRequest(BaseModel):
    professional_id: uuid.UUID


def _issue_session_cookie(
    response: Response,
    *,
    user_id: uuid.UUID,
    email: str,
    role: str,
    professional_id: uuid.UUID | None,
    impersonating: bool = False,
) -> None:
    access_token = create_access_token(
        data={
            "sub": str(user_id),
            "email": email,
            "role": role,
            "professional_id": str(professional_id) if professional_id else None,
            "impersonating": impersonating,
        }
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        samesite="lax",
    )


@router.post("/login")
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email, User.status == "active").first()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    _issue_session_cookie(
        response,
        user_id=user.id,
        email=user.email,
        role=user.role,
        professional_id=user.professional_id,
    )
    return {"email": user.email, "role": user.role}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return {"message": "Successfully logged out"}


@router.get("/me")
def me(
    response: Response,
    user: dict = Depends(require_authenticated),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    professional_name = None
    features: list[str] = []
    if user["professional_id"] is not None:
        professional_id = uuid.UUID(user["professional_id"])
        professional = (
            db.query(Professional).filter(Professional.id == professional_id).first()
        )
        professional_name = professional.name if professional else None
        if is_tenant_feature_enabled(db, professional_id, COMMERCIAL_FINANCIALS):
            features.append(COMMERCIAL_FINANCIALS)

    return {**user, "professional_name": professional_name, "features": features}


@router.post("/impersonate")
def impersonate(
    body: ImpersonateRequest,
    response: Response,
    admin: dict = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    professional = db.query(Professional).filter(Professional.id == body.professional_id).first()
    if professional is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    db.add(
        ImpersonationLog(
            admin_user_id=uuid.UUID(admin["user_id"]),
            professional_id=professional.id,
        )
    )
    db.commit()

    _issue_session_cookie(
        response,
        user_id=uuid.UUID(admin["user_id"]),
        email=admin["email"],
        role="platform_admin",
        professional_id=professional.id,
        impersonating=True,
    )
    return {"professional_id": str(professional.id), "professional_name": professional.name}


@router.post("/stop-impersonating")
def stop_impersonating(response: Response, admin: dict = Depends(require_platform_admin)):
    """Return to the tenant tile grid without a tenant selected."""
    _issue_session_cookie(
        response,
        user_id=uuid.UUID(admin["user_id"]),
        email=admin["email"],
        role="platform_admin",
        professional_id=None,
        impersonating=False,
    )
    return {"message": "Stopped impersonating"}
