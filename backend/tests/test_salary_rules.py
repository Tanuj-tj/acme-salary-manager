"""Salary amount business rules."""

from __future__ import annotations

import pytest

from app.core.errors import InvalidSalaryAmountError
from app.domain.money import Money
from app.domain.salary_rules import validate_salary_amount


class TestValidateSalaryAmount:
    def test_positive_amount_is_valid(self) -> None:
        validate_salary_amount(Money.of(8_500_000, "GBP"))

    def test_smallest_positive_amount_is_valid(self) -> None:
        validate_salary_amount(Money.of(1, "GBP"))

    def test_zero_is_rejected(self) -> None:
        """Zero would silently drag down every average that includes it."""
        with pytest.raises(InvalidSalaryAmountError, match="greater than zero"):
            validate_salary_amount(Money.of(0, "USD"))

    @pytest.mark.parametrize("amount_minor", [-1, -100, -8_500_000])
    def test_negative_amounts_are_rejected(self, amount_minor: int) -> None:
        with pytest.raises(InvalidSalaryAmountError):
            validate_salary_amount(Money.of(amount_minor, "USD"))

    def test_error_carries_context_for_the_caller(self) -> None:
        with pytest.raises(InvalidSalaryAmountError) as exc_info:
            validate_salary_amount(Money.of(-500, "EUR"))
        assert exc_info.value.context == {"amount_minor": -500, "currency_code": "EUR"}
