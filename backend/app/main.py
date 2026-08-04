"""
FastAPI application entry point.

Start with:
    cd backend && python -m uvicorn app.main:app --reload --port 8005
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.calendar import router as calendar_router

app = FastAPI(
    title="Agenda AI",
    description="WhatsApp Schedule Copilot — Web Calendar API",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# CORS — allow the Next.js dev server during development
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(calendar_router)


@app.get("/health")
def health():
    return {"status": "ok"}
