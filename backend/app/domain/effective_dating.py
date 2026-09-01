"""Effective-dating logic for time-bounded records.

Intervals are **half-open**: ``[effective_from, effective_to)``. A null
``effective_to`` means "still in effect".

Half-open is chosen deliberately -- it lets consecutive records abut exactly
(one ends the day the next begins) with neither a one-day gap nor a one-day
double count. Interval boundaries are where effective-dating bugs live, so this
convention is applied everywhere without exception.

Pure: no I/O, no ambient clock.
"""

from __future__ import annotations

from datetime import date

from app.core.errors import InvalidEffectivePeriodError


def validate_period(effective_from: date, effective_to: date | None) -> None:
    """Raise if the period is not a valid half-open interval.

    A zero-width period (``effective_to == effective_from``) is rejected: it is
    in effect on no day at all, which is never what the user meant.
    """
    if effective_to is None:
        return
    if effective_to <= effective_from:
        raise InvalidEffectivePeriodError(
            f"effective_to ({effective_to.isoformat()}) must be after "
            f"effective_from ({effective_from.isoformat()})",
            context={
                "effective_from": effective_from.isoformat(),
                "effective_to": effective_to.isoformat(),
            },
        )


def is_effective_on(effective_from: date, effective_to: date | None, on_date: date) -> bool:
    """Return whether a record with this period is in effect on ``on_date``."""
    if on_date < effective_from:
        return False
    return effective_to is None or on_date < effective_to


def periods_overlap(
    a_from: date,
    a_to: date | None,
    b_from: date,
    b_to: date | None,
) -> bool:
    """Return whether two half-open periods share at least one day."""
    a_ends_before_b_starts = a_to is not None and a_to <= b_from
    b_ends_before_a_starts = b_to is not None and b_to <= a_from
    return not (a_ends_before_b_starts or b_ends_before_a_starts)
