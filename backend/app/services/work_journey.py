"""Work journey (daily schedule) validation and persistence."""

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.work_journey_interval import WorkJourneyInterval
from app.schemas.rules import WorkJourneyIntervalInput, WorkJourneyReplace


def assert_work_journey_is_valid(body: WorkJourneyReplace) -> None:
    for day in range(7):
        day_intervals = [
            interval for interval in body.intervals if interval.day_of_week == day
        ]
        work_ranges = sorted(
            (interval.start_time, interval.end_time)
            for interval in day_intervals
            if interval.interval_type == "work"
        )
        break_ranges = sorted(
            (interval.start_time, interval.end_time)
            for interval in day_intervals
            if interval.interval_type == "break"
        )
        for ranges in (work_ranges, break_ranges):
            if any(
                current[0] < previous[1]
                for previous, current in zip(ranges, ranges[1:])
            ):
                raise HTTPException(
                    status_code=422,
                    detail="Journey intervals of the same type must not overlap",
                )
        for break_start, break_end in break_ranges:
            if not any(
                work_start <= break_start and work_end >= break_end
                for work_start, work_end in work_ranges
            ):
                raise HTTPException(
                    status_code=422,
                    detail="Break intervals must be contained in a work interval",
                )


def get_work_journey(
    db: Session,
    professional_id: uuid.UUID,
) -> list[WorkJourneyInterval]:
    return (
        db.query(WorkJourneyInterval)
        .filter(WorkJourneyInterval.professional_id == professional_id)
        .order_by(
            WorkJourneyInterval.day_of_week,
            WorkJourneyInterval.start_time,
        )
        .all()
    )


def replace_work_journey_intervals(
    db: Session,
    professional_id: uuid.UUID,
    intervals: list[WorkJourneyIntervalInput],
) -> tuple[list[dict], list[WorkJourneyInterval]]:
    previous_rows = get_work_journey(db, professional_id)
    previous = [
        {
            "day_of_week": interval.day_of_week,
            "interval_type": interval.interval_type,
            "start_time": interval.start_time.isoformat(),
            "end_time": interval.end_time.isoformat(),
        }
        for interval in previous_rows
    ]
    db.query(WorkJourneyInterval).filter(
        WorkJourneyInterval.professional_id == professional_id
    ).delete(synchronize_session=False)
    db.add_all(
        [
            WorkJourneyInterval(
                professional_id=professional_id,
                day_of_week=interval.day_of_week,
                interval_type=interval.interval_type,
                start_time=interval.start_time,
                end_time=interval.end_time,
            )
            for interval in intervals
        ]
    )
    db.flush()
    return previous, get_work_journey(db, professional_id)
