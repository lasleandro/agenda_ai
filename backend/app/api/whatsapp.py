"""
YCloud WhatsApp webhook (Phase 1 — brief Section 12.1).

Verifies signature, then delegates to the shared ingestion logic (persist,
normalize, idempotency, debounce reset). No synchronous LLM calls happen
here.
"""

import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.chat.ingestion import ingest_event
from app.chat.ycloud_provider import verify_signature, webhook_signing_secret

router = APIRouter(prefix="/webhooks", tags=["whatsapp"])

logger = logging.getLogger(__name__)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/ycloud")
async def ycloud_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    secret = webhook_signing_secret()

    if secret:
        if not verify_signature(raw_body, request.headers.get("ycloud-signature"), secret):
            logger.warning("YCloud webhook signature verification failed")
            return Response(status_code=401)
    else:
        logger.warning("YCLOUD_WEBHOOK_SIGNING_SECRET not set — skipping signature verification")

    event = await request.json()
    ingest_event(db, event)

    return Response(status_code=200)
