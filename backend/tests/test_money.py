"""Money value object: exact arithmetic and currency safety.

Pure unit tests -- no database, no clock, no network.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.errors import CurrencyMismatchError, InvalidSalaryAmountError
from app.domain.money import Money


class TestConstruction:
    def test_of_builds_from_minor_units(self) -> None:
        money = Money.of(8_500_000, "GBP")
        assert money.amount_minor == 8_500_000
        assert money.currency_code == "GBP"
        assert money.to_major() == Decimal("85000.00")

    def test_from_major_scales_by_currency_precision(self) -> None:
        assert Money.from_major(Decimal("85000.00"), "USD").amount_minor == 8_500_000

    def test_from_major_respects_zero_minor_unit_currencies(self) -> None:
        """JPY has no minor unit; assuming 2 digits would be 100x wrong."""
        yen = Money.from_major(Decimal("9500000"), "JPY")
        assert yen.amount_minor == 9_500_000
        assert yen.to_major() == Decimal("9500000")

    def test_from_major_rounds_half_up(self) -> None:
        assert Money.from_major(Decimal("10.005"), "USD").amount_minor == 1001

    def test_from_major_rejects_float(self) -> None:
        """Accepting a float would reintroduce the drift Money exists to stop."""
        with pytest.raises(InvalidSalaryAmountError, match="float"):
            Money.from_major(85000.00, "USD")  # type: ignore[arg-type]

    def test_rejects_non_integer_minor_units(self) -> None:
        with pytest.raises(InvalidSalaryAmountError):
            Money(amount_minor=100.5, currency=Money.of(1, "USD").currency)  # type: ignore[arg-type]

    def test_rejects_bool_as_amount(self) -> None:
        """bool is a subtype of int, so the type checker will not catch this.

        That is precisely why Money checks at runtime: `True` would otherwise
        be silently stored as an amount of 1 minor unit.
        """
        with pytest.raises(InvalidSalaryAmountError):
            Money(amount_minor=True, currency=Money.of(1, "USD").currency)


class TestArithmetic:
    def test_addition_is_exact(self) -> None:
        total = Money.of(3_333_333, "USD") + Money.of(6_666_667, "USD")
        assert total.amount_minor == 10_000_000

    def test_summing_many_amounts_does_not_drift(self) -> None:
        """The float failure mode this type prevents, at 10,000-employee scale."""
        total = Money.of(0, "USD")
        for _ in range(10_000):
            total = total + Money.of(10, "USD")  # 0.10 USD
        assert total.amount_minor == 100_000
        assert total.to_major() == Decimal("1000.00")

    def test_subtraction(self) -> None:
        assert (Money.of(500, "EUR") - Money.of(200, "EUR")).amount_minor == 300

    def test_comparison(self) -> None:
        assert Money.of(100, "USD") < Money.of(200, "USD")
        assert Money.of(200, "USD") >= Money.of(200, "USD")

    def test_equality_distinguishes_currency(self) -> None:
        assert Money.of(100, "USD") != Money.of(100, "EUR")


class TestCurrencySafety:
    def test_addition_across_currencies_raises(self) -> None:
        with pytest.raises(CurrencyMismatchError, match="explicit exchange rate"):
            _ = Money.of(100, "USD") + Money.of(100, "EUR")

    def test_subtraction_across_currencies_raises(self) -> None:
        with pytest.raises(CurrencyMismatchError):
            _ = Money.of(100, "USD") - Money.of(100, "GBP")

    def test_comparison_across_currencies_raises(self) -> None:
        """100 JPY vs 100 USD is not a meaningful comparison without a rate."""
        with pytest.raises(CurrencyMismatchError):
            _ = Money.of(100, "JPY") < Money.of(100, "USD")
