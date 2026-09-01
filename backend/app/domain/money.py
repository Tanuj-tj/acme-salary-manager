"""Money value object.

Two rules this type exists to enforce:

1. Money is stored as integer minor units, never a float. Binary floating point
   drift is visible once you sum thousands of salaries.
2. An amount is inseparable from its currency, and arithmetic across currencies
   raises rather than silently coercing.

Pure: no I/O, no clock, no ORM. Conversion between currencies lives elsewhere
and requires an explicit rate, because it is not a property of Money alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Self

from app.core.errors import CurrencyMismatchError, InvalidSalaryAmountError
from app.domain.currencies import Currency, get_currency


@dataclass(frozen=True, slots=True, order=False)
class Money:
    """An exact monetary amount in a single currency."""

    amount_minor: int
    currency: Currency

    def __post_init__(self) -> None:
        if isinstance(self.amount_minor, bool) or not isinstance(self.amount_minor, int):
            raise InvalidSalaryAmountError(
                "Money amount must be an integer number of minor units, "
                f"got {type(self.amount_minor).__name__}"
            )

    # -- construction ---------------------------------------------------

    @classmethod
    def of(cls, amount_minor: int, currency_code: str) -> Self:
        """Build from minor units and a currency code, validating the code."""
        return cls(amount_minor=amount_minor, currency=get_currency(currency_code))

    @classmethod
    def from_major(cls, amount: Decimal | int | str, currency_code: str) -> Self:
        """Build from a major-unit amount (e.g. ``Decimal("1234.56")``).

        Rounds half-up to the currency's minor-unit precision. ``float`` is
        rejected outright -- accepting it would reintroduce the drift this type
        exists to prevent.
        """
        if isinstance(amount, float):
            raise InvalidSalaryAmountError(
                "Refusing to build Money from a float; pass Decimal, int or str"
            )

        currency = get_currency(currency_code)
        try:
            major = Decimal(amount)
        except (ArithmeticError, ValueError) as exc:
            raise InvalidSalaryAmountError(f"Not a valid decimal amount: {amount!r}") from exc

        if not major.is_finite():
            raise InvalidSalaryAmountError(f"Amount must be finite, got {amount!r}")

        scale = Decimal(10) ** currency.minor_unit_digits
        minor = (major * scale).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        return cls(amount_minor=int(minor), currency=currency)

    # -- accessors ------------------------------------------------------

    @property
    def currency_code(self) -> str:
        return self.currency.code

    def to_major(self) -> Decimal:
        """Return the amount in major units, exact to the currency's precision."""
        scale = Decimal(10) ** self.currency.minor_unit_digits
        return (Decimal(self.amount_minor) / scale).quantize(
            Decimal(1).scaleb(-self.currency.minor_unit_digits)
        )

    # -- arithmetic -----------------------------------------------------

    def _assert_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot combine {self.currency_code} and {other.currency_code} "
                "without an explicit exchange rate",
                context={"left": self.currency_code, "right": other.currency_code},
            )

    def __add__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount_minor, self.currency)

    def __lt__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount_minor < other.amount_minor

    def __le__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount_minor <= other.amount_minor

    def __gt__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount_minor > other.amount_minor

    def __ge__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount_minor >= other.amount_minor

    @property
    def is_positive(self) -> bool:
        return self.amount_minor > 0

    def __str__(self) -> str:
        return f"{self.to_major()} {self.currency_code}"
