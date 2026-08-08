"""Contracts for operational rules (work journey, make-up cancellation notice window)."""

import uuid
from datetime import time
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class WorkJourneyIntervalInput(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    interval_type: Literal["work", "break"]
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def validate_time_range(self) -> Self:
        if self.end_time <= self.start_time:
            raise ValueError("Journey intervals must end after they start")
        return self


class WorkJourneyIntervalDetail(WorkJourneyIntervalInput):
    id: uuid.UUID


class WorkJourneyReplace(BaseModel):
    intervals: list[WorkJourneyIntervalInput]


class CancellationNoticeHoursDetail(BaseModel):
    cancellation_notice_hours: int


class CancellationNoticeHoursUpdate(BaseModel):
    cancellation_notice_hours: int = Field(ge=0, le=168)
