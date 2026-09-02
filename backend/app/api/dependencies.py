"""
Shared FastAPI dependencies.
"""

import uuid

from fastapi import Depends, HTTPException, Request
import jwt

from app.core.security import SESSION_COOKIE_NAME, decode_access_token
from app.core.settings import allowed_origins, is_production
from app.database import SessionLocal
from app.models import User
from app.services.tenant_features import COMMERCIAL_FINANCIALS, is_tenant_feature_enabled


def require_authenticated(request: Request) -> dict:
    """Dependency that requires a valid Agenda session cookie.

    Returns {"user_id", "email", "role", "professional_id", "impersonating"}.
    professional_id is None for a platform_admin who hasn't impersonated a
    tenant yet.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if request.method not in {"GET", "HEAD", "OPTIONS"} and is_production():
        origin = request.headers.get("origin", "").rstrip("/")
        if origin not in allowed_origins():
            raise HTTPException(status_code=403, detail="Invalid request origin")

    try:
        user_id = uuid.UUID(payload["sub"])
        token_auth_version = int(payload["auth_version"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None or user.status != "active" or user.auth_version != token_auth_version:
            raise HTTPException(status_code=401, detail="Session is no longer active")

        professional_id = None
        impersonating = False
        if user.role == "professional":
            professional_id = str(user.professional_id) if user.professional_id else None
        elif user.role == "platform_admin":
            selected = payload.get("professional_id")
            if selected is not None:
                try:
                    professional_id = str(uuid.UUID(selected))
                    impersonating = bool(payload.get("impersonating", False))
                except (TypeError, ValueError):
                    raise HTTPException(status_code=401, detail="Invalid token")
        return {
            "user_id": str(user.id),
            "email": user.email,
            "role": user.role,
            "professional_id": professional_id,
            "impersonating": impersonating,
        }
    finally:
        db.close()


def require_professional_id(user: dict = Depends(require_authenticated)) -> uuid.UUID:
    """Dependency for tenant-scoped routes. Resolves the professional_id every
    query must filter by — never trust a client-supplied tenant id instead.

    Raises 403 for a platform_admin who hasn't impersonated a tenant yet.
    """
    professional_id = user.get("professional_id")
    if professional_id is None:
        raise HTTPException(status_code=403, detail="No tenant selected — impersonate a tenant first")
    return uuid.UUID(professional_id)


def require_platform_admin(user: dict = Depends(require_authenticated)) -> dict:
    """Dependency for platform-admin-only routes (tenant list, impersonate)."""
    if user.get("role") != "platform_admin":
        raise HTTPException(status_code=403, detail="Platform admin access required")
    return user


def require_tenant_feature(feature_key: str):
    """Build a tenant-scoped dependency that rejects disabled optional modules."""

    def dependency(
        professional_id: uuid.UUID = Depends(require_professional_id),
    ) -> uuid.UUID:
        db = SessionLocal()
        try:
            if not is_tenant_feature_enabled(db, professional_id, feature_key):
                raise HTTPException(status_code=404, detail="Feature not available")
        finally:
            db.close()
        return professional_id

    return dependency


require_commercial_financials = require_tenant_feature(COMMERCIAL_FINANCIALS)
