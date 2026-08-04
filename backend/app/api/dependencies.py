"""
Shared FastAPI dependencies.
"""

from fastapi import HTTPException, Request
import jwt

from app.core.security import decode_access_token


def require_authenticated(request: Request) -> dict:
    """Dependency that requires a valid access_token cookie. Returns {"username"}."""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"username": payload.get("sub")}
