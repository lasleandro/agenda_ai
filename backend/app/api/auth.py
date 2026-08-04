"""
Auth routes — single admin user, JWT cookie session.

POST /api/auth/login  — validate credentials against ADMIN_USERNAME/ADMIN_PASSWORD
                         (.env), set an httpOnly JWT cookie.
POST /api/auth/logout — clear the cookie.
GET  /api/auth/me     — return the current session's username, or 401.
"""

import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.api.dependencies import require_authenticated
from app.core.security import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest, response: Response):
    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        raise HTTPException(status_code=500, detail="Admin credentials not configured")

    valid = secrets.compare_digest(body.username, ADMIN_USERNAME) and secrets.compare_digest(
        body.password, ADMIN_PASSWORD
    )
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(data={"sub": body.username})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
    )
    return {"username": body.username}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="access_token")
    return {"message": "Successfully logged out"}


@router.get("/me")
def me(user: dict = Depends(require_authenticated)):
    return user
