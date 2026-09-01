"""Effective-dating interval logic.

Boundaries get explicit coverage: half-open intervals are correct precisely at
the edges, and that is where off-by-one bugs would silently double-count an
employee in a payroll total.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.core.errors import InvalidEffectivePeriodError
from app.domain.effective_dating import is_effective_on, periods_overlap, validate_period

JAN = date(2024, 1, 1)
JUL = date(2024, 7, 1)
DEC = date(2024, 12, 31)


class TestValidatePeriod:
    def test_open_ended_period_is_valid(self) -> None:
        validate_period(JAN, None)

    def test_closed_period_is_valid(self) -> None:
        validate_period(JAN, JUL)

    def test_end_before_start_raises(self) -> None:
        with pytest.raises(InvalidEffectivePeriodError):
            validate_period(JUL, JAN)

    def test_zero_width_period_raises(self) -> None:
        """A period in effect on no day at all is never what was meant."""
        with pytest.raises(InvalidEffectivePeriodError):
            validate_period(JAN, JAN)


class TestIsEffectiveOn:
    def test_start_date_is_included(self) -> None:
        assert is_effective_on(JAN, JUL, JAN)

    def test_end_date_is_excluded(self) -> None:
        """Half-open: the record is no longer in effect on its end date."""
        assert not is_effective_on(JAN, JUL, JUL)

    def test_day_before_end_is_included(self) -> None:
        assert is_effective_on(JAN, JUL, date(2024, 6, 30))

    def test_before_start_is_excluded(self) -> None:
        assert not is_effective_on(JUL, None, JAN)

    def test_open_ended_covers_all_later_dates(self) -> None:
        assert is_effective_on(JAN, None, DEC)


class TestPeriodsOverlap:
    def test_abutting_periods_do_not_overlap(self) -> None:
        """[Jan, Jul) and [Jul, Dec) share no day -- the raise-day boundary."""
        assert not periods_overlap(JAN, JUL, JUL, DEC)

    def test_identical_periods_overlap(self) -> None:
        assert periods_overlap(JAN, JUL, JAN, JUL)

    def test_partially_overlapping_periods(self) -> None:
        assert periods_overlap(JAN, DEC, JUL, None)

    def test_disjoint_periods_do_not_overlap(self) -> None:
        assert not periods_overlap(JAN, date(2024, 3, 1), JUL, DEC)

    def test_two_open_ended_periods_always_overlap(self) -> None:
        assert periods_overlap(JAN, None, JUL, None)

    def test_open_ended_overlaps_later_closed_period(self) -> None:
        assert periods_overlap(JAN, None, JUL, DEC)

    def test_overlap_is_symmetric(self) -> None:
        assert periods_overlap(JAN, JUL, JUL, DEC) == periods_overlap(JUL, DEC, JAN, JUL)
