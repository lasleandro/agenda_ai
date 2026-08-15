"""
FastAPI application entry point.

Start with:
    cd backend && python -m uvicorn app.main:app --reload --port 8005
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
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

app = FastAPI(
    title="Tennis OS",
    description="WhatsApp Schedule Copilot — Web Calendar API",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# CORS — allow the Next.js dev server during development
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3010",
        "http://127.0.0.1:3010",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)
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

if os.getenv("DEBUG", "").lower() == "true":
    from app.api.dev_mock import router as dev_mock_router

    app.include_router(dev_mock_router)


@app.get("/health")
def health():
    return {"status": "ok"}
