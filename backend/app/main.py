"""
FastAPI application entry point.

Start with:
    cd backend && python -m uvicorn app.main:app --reload --port 8005
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.admin_account_requests import router as admin_account_requests_router
from app.api.account_requests import router as account_requests_router
from app.api.appointment_candidates import router as appointment_candidates_router
from app.api.assistant import router as assistant_router
from app.api.auth import router as auth_router
from app.api.calendar import router as calendar_router
from app.api.contacts import router as contacts_router
from app.api.conversations import router as conversations_router
from app.api.financial import router as financial_router
from app.api.financial_analytics import router as financial_analytics_router
from app.api.instructor_events import router as instructor_events_router
from app.api.places import router as places_router
from app.api.recurring_slots import router as recurring_slots_router
from app.api.revenue import router as revenue_router
from app.api.rules import router as rules_router
from app.api.waitlist import router as waitlist_router
from app.api.whatsapp import router as whatsapp_router
from app.api.whatsapp_connection import router as whatsapp_connection_router
from app.core.settings import allowed_origins, is_production, validate_startup_settings

# Interactive API docs and the raw OpenAPI schema are disabled in production
# so the endpoint surface is not enumerable by anonymous clients.
_docs_disabled = is_production()

app = FastAPI(
    title="Tennis OS",
    description="WhatsApp Schedule Copilot — Web Calendar API",
    version="0.1.0",
    docs_url=None if _docs_disabled else "/docs",
    redoc_url=None if _docs_disabled else "/redoc",
    openapi_url=None if _docs_disabled else "/openapi.json",
)

# ---------------------------------------------------------------------------
# CORS — allow the Next.js dev server during development
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def validate_production_configuration() -> None:
    """Fail early when production authentication/email settings are unsafe."""
    validate_startup_settings()
    if is_production():
        from app.integrations.email.smtp import SmtpEmailSender

        SmtpEmailSender()


@app.middleware("http")
async def rate_limit_writes(request, call_next):
    """Per-instance burst guard for state-changing API calls (production only)."""
    if is_production() and request.method.upper() not in ("GET", "HEAD", "OPTIONS", "TRACE"):
        if request.url.path.startswith("/api/"):
            from app.core import error_codes
            from app.core.error_responses import error_response
            from app.core.rate_limit import write_limiter

            client_ip = request.client.host if request.client else "unknown"
            if not write_limiter.is_allowed(client_ip):
                return error_response(
                    429, error_codes.RATE_LIMITED, "Too many requests. Try again shortly."
                )
    return await call_next(request)


@app.middleware("http")
async def csrf_protect(request, call_next):
    """Reject cookie-authenticated writes without a matching CSRF header.

    Production only — see app.core.csrf. Webhooks are under /webhooks and are
    authenticated by provider signature, so they are never in scope here.
    """
    if is_production():
        from app.core import error_codes
        from app.core.csrf import (
            CSRF_HEADER_NAME,
            csrf_check_required,
            csrf_header_matches_cookie,
        )
        from app.core.error_responses import error_response

        if csrf_check_required(request.method, request.url.path, request.cookies):
            header_value = request.headers.get(CSRF_HEADER_NAME)
            if not csrf_header_matches_cookie(header_value, request.cookies):
                return error_response(
                    403, error_codes.CSRF_TOKEN_INVALID, "Invalid or missing CSRF token."
                )
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request, call_next):
    """Apply conservative browser hardening without changing API responses."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
    if is_production():
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

app.include_router(admin_router)
app.include_router(admin_account_requests_router)
app.include_router(account_requests_router)
app.include_router(appointment_candidates_router)
app.include_router(assistant_router)
app.include_router(auth_router)
app.include_router(calendar_router)
app.include_router(contacts_router)
app.include_router(conversations_router)
app.include_router(financial_router)
app.include_router(financial_analytics_router)
app.include_router(instructor_events_router)
app.include_router(places_router)
app.include_router(recurring_slots_router)
app.include_router(revenue_router)
app.include_router(rules_router)
app.include_router(waitlist_router)
app.include_router(whatsapp_router)
app.include_router(whatsapp_connection_router)

if os.getenv("DEBUG", "").lower() == "true" or os.getenv("ENABLE_MOCK_CHAT", "").lower() == "true":
    from app.api.dev_mock import router as dev_mock_router

    app.include_router(dev_mock_router)


@app.get("/health")
def health():
    return {"status": "ok"}
