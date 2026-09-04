"""Contracts for public account requests and platform-admin review."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.api import TenantSummary

AccountRequestStatus = Literal["pending", "approved", "rejected"]
ActivationState = Literal[
    "not_queued",
    "queued",
    "processing",
    "retry_wait",
    "sent",
    "failed",
    "suppressed",
    "account_activated",
]


class AccountRequestSubmit(BaseModel):
    """Anonymous request for a manually reviewed platform account."""

    proposed_tenant_name: str = Field(min_length=2, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    whatsapp: str = Field(min_length=3, max_length=30)
    message: str | None = Field(default=None, max_length=1000)

    @field_validator("proposed_tenant_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Name must contain at least two characters")
        return cleaned

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class AccountRequestPublicResponse(BaseModel):
    """Generic response that does not disclose account/request existence."""

    message: str


class AccountRequestAdminItem(BaseModel):
    """Admin-only request detail with safe activation state."""

    id: uuid.UUID
    proposed_tenant_name: str
    email: str
    whatsapp: str | None
    message: str | None
    status: AccountRequestStatus
    submitted_at: datetime
    reviewed_at: datetime | None
    reviewer_email: str | None
    decision_reason: str | None
    professional_id: uuid.UUID | None
    owner_user_id: uuid.UUID | None
    activation_state: ActivationState | None


class AccountRequestStatusCounts(BaseModel):
    pending: int
    approved: int
    rejected: int


class AccountRequestAdminListResponse(BaseModel):
    requests: list[AccountRequestAdminItem]
    page: int
    page_size: int
    total: int
    total_pages: int
    status_counts: AccountRequestStatusCounts


class AccountRequestSummaryResponse(BaseModel):
    pending: int


class AccountRequestMetricsResponse(BaseModel):
    pending: int
    approved: int
    rejected: int
    oldest_pending_timestamp: float | None
    pending_over_24h: int


class AccountRequestApprove(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=255)
    whatsapp: str = Field(min_length=3, max_length=30)
    timezone: str = Field(default="America/Sao_Paulo", min_length=1, max_length=100)

    @field_validator("tenant_name")
    @classmethod
    def normalize_tenant_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Tenant name must contain at least two characters")
        return cleaned

    @field_validator("timezone")
    @classmethod
    def normalize_timezone(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Timezone is required")
        return cleaned


class AccountRequestReject(BaseModel):
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class AccountRequestDecisionResponse(BaseModel):
    request: AccountRequestAdminItem
    tenant: TenantSummary | None = None


class AccountActivationResendResponse(BaseModel):
    request_id: uuid.UUID
    activation_state: ActivationState
