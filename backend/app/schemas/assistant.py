"""API schemas for the instructor assistant chat (operational ontology
roadmap v0.2, Phase 2 web-chat adapter; Phase 3 action-candidate
confirm/reject)."""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class AssistantMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AssistantChatRequest(BaseModel):
    messages: list[AssistantMessage] = Field(min_length=1, max_length=40)
    recent_candidate_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5)


class ToolCallTraceDetail(BaseModel):
    name: str
    arguments: dict
    result_summary: str


class PendingActionCandidate(BaseModel):
    id: uuid.UUID
    preview_text: str
    advisory_text: str | None = None
    affected_entities: list[dict[str, Any]]
    expires_at: str


class AssistantChatResponse(BaseModel):
    reply: str
    tool_calls: list[ToolCallTraceDetail]
    pending_candidate: PendingActionCandidate | None = None


class ActionCandidateResultResponse(BaseModel):
    status: str
    summary: str
