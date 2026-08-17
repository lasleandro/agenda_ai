"""Provider-aware WhatsApp webhook boundary."""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.chat.ingestion import ingest_provider_webhook
from app.integrations.whatsapp.contracts import WhatsAppPermanentError
from app.integrations.whatsapp.registry import get_whatsapp_provider

router = APIRouter(prefix="/webhooks", tags=["whatsapp"])

logger = logging.getLogger(__name__)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _debug_mode() -> bool:
    return os.getenv("DEBUG", "").casefold() == "true"


async def _handle_webhook(
    provider_key: str, request: Request, db: Session
) -> Response:
    try:
        provider = get_whatsapp_provider(provider_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="WhatsApp provider not found") from exc

    raw_body = await request.body()
    if not provider.verify_webhook(raw_body, request.headers):
        if not _debug_mode():
            logger.warning("Rejected WhatsApp webhook signature (provider=%s)", provider.key)
            return Response(status_code=401)
        logger.warning(
            "Accepting unverified WhatsApp webhook in DEBUG mode (provider=%s)",
            provider.key,
        )

    try:
        ingest_provider_webhook(db, raw_body, provider)
    except WhatsAppPermanentError:
        logger.warning("Rejected malformed WhatsApp webhook (provider=%s)", provider.key)
        return Response(status_code=400)

    return Response(status_code=200)


@router.post("/whatsapp/{provider_key}")
async def whatsapp_webhook(
    provider_key: str, request: Request, db: Session = Depends(get_db)
) -> Response:
    """Receive a selected provider callback through the canonical dispatcher."""
    return await _handle_webhook(provider_key, request, db)


@router.post("/ycloud")
async def ycloud_webhook(
    request: Request, db: Session = Depends(get_db)
) -> Response:
    """Temporary compatibility callback for the current YCloud registration."""
    return await _handle_webhook("ycloud", request, db)
