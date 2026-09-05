"""Provider-aware WhatsApp webhook boundary.

The endpoint does the minimum that must happen inside the provider request:
resolve the provider, read the raw body once, verify the signature, and
durably hand the delivery off (``webhook_receipts`` +
``get_webhook_task_queue()``). Ingestion, LLM turns, and outbound sends run
afterwards — in the webhook processor worker, or inline in local
development — so provider acknowledgement never waits on them and retries
are idempotent on the receipt key.
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.integrations.tasks import get_webhook_task_queue
from app.integrations.whatsapp.registry import get_whatsapp_provider

router = APIRouter(prefix="/webhooks", tags=["whatsapp"])

logger = logging.getLogger(__name__)

MAX_WEBHOOK_BODY_BYTES = 1024 * 1024


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _debug_mode() -> bool:
    return os.getenv("DEBUG", "").casefold() == "true"


async def _read_webhook_body(request: Request) -> bytes | None:
    """Read a bounded raw webhook body without parsing or reserializing it."""
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = 0
        if declared_size > MAX_WEBHOOK_BODY_BYTES:
            logger.warning("Rejected oversized WhatsApp webhook body")
            return None

    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if len(chunks) > MAX_WEBHOOK_BODY_BYTES:
            logger.warning("Rejected oversized WhatsApp webhook body")
            return None
    return bytes(chunks)


async def _handle_webhook(
    provider_key: str, request: Request, db: Session
) -> Response:
    try:
        provider = get_whatsapp_provider(provider_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="WhatsApp provider not found") from exc

    raw_body = await _read_webhook_body(request)
    if raw_body is None:
        return Response(status_code=413)
    if not provider.verify_webhook(raw_body, request.headers):
        if not _debug_mode():
            logger.warning("Rejected WhatsApp webhook signature (provider=%s)", provider.key)
            return Response(status_code=401)
        logger.warning(
            "Accepting unverified WhatsApp webhook in DEBUG mode (provider=%s)",
            provider.key,
        )

    result = get_webhook_task_queue().enqueue(db, provider.key, raw_body)
    if not result.accepted:
        # Handoff failed transiently — let the provider retry.
        return Response(status_code=503)
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
