"""Domain enumerations.

Stored as short strings with a CHECK constraint rather than a native database
ENUM type, so the same schema works on SQLite and PostgreSQL.
"""

from __future__ import annotations

from enum import StrEnum


class EmploymentStatus(StrEnum):
    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    TERMINATED = "terminated"


class PayType(StrEnum):
    """The compensation element a salary record represents."""

    BASE = "base"
    BONUS = "bonus"
    ALLOWANCE = "allowance"


class PayPeriod(StrEnum):
    """The period the recorded amount covers, before annualisation."""

    ANNUAL = "annual"
    MONTHLY = "monthly"
    HOURLY = "hourly"


class SalaryChangeReason(StrEnum):
    HIRE = "hire"
    MERIT = "merit"
    PROMOTION = "promotion"
    MARKET_ADJUSTMENT = "market_adjustment"
    DEMOTION = "demotion"
    CORRECTION = "correction"
    OTHER = "other"
