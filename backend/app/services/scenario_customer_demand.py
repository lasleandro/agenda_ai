"""Explainable customer-base estimates for financial scenarios."""

from datetime import date
from math import ceil

from app.schemas.financial import FinancialScenarioCustomerEstimate


def estimate_customer_range(
    participant_hours: float,
    date_from: date,
    date_to: date,
) -> FinancialScenarioCustomerEstimate:
    """Estimate the active customer base needed for a scenario.

    The range assumes each active customer attends between one and three hours
    per calendar week. Partial periods count as one calendar week so a short
    simulation never implies an impossible fractional customer base.
    """
    calendar_weeks = max(1, ceil(((date_to - date_from).days + 1) / 7))
    weekly_participant_hours = participant_hours / calendar_weeks
    return FinancialScenarioCustomerEstimate(
        calendar_weeks=calendar_weeks,
        weekly_participant_hours=round(weekly_participant_hours, 1),
        minimum_customers=ceil(weekly_participant_hours / 3),
        maximum_customers=ceil(weekly_participant_hours),
    )
