"""Supported currency registry.

``minor_unit_digits`` is not decoration: JPY has no minor unit, so hardcoding
"divide by 100" reports Japanese salaries 100x too small. Every conversion
between major and minor units must go through this registry.

Held in code rather than a table for now. It is small, static, and needed by
pure domain functions that must not touch a database. It moves to a reference
table if and when currencies become user-manageable.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import UnsupportedCurrencyError


@dataclass(frozen=True, slots=True)
class Currency:
    code: str
    name: str
    minor_unit_digits: int


_CURRENCIES: tuple[Currency, ...] = (
    Currency("USD", "US Dollar", 2),
    Currency("EUR", "Euro", 2),
    Currency("GBP", "Pound Sterling", 2),
    Currency("CHF", "Swiss Franc", 2),
    Currency("SEK", "Swedish Krona", 2),
    Currency("PLN", "Polish Zloty", 2),
    Currency("CAD", "Canadian Dollar", 2),
    Currency("MXN", "Mexican Peso", 2),
    Currency("BRL", "Brazilian Real", 2),
    Currency("INR", "Indian Rupee", 2),
    Currency("SGD", "Singapore Dollar", 2),
    Currency("AUD", "Australian Dollar", 2),
    Currency("AED", "UAE Dirham", 2),
    Currency("ZAR", "South African Rand", 2),
    Currency("JPY", "Japanese Yen", 0),
)

CURRENCIES: dict[str, Currency] = {currency.code: currency for currency in _CURRENCIES}

SUPPORTED_CURRENCY_CODES: frozenset[str] = frozenset(CURRENCIES)


def is_supported_currency(code: str) -> bool:
    return code in SUPPORTED_CURRENCY_CODES


def get_currency(code: str) -> Currency:
    """Look up a currency by ISO 4217 code.

    Raises:
        UnsupportedCurrencyError: if the code is unknown. Never falls back to a
            default -- guessing the currency of a salary is worse than failing.
    """
    if not isinstance(code, str):  # pragma: no cover - defensive
        raise UnsupportedCurrencyError(f"Currency code must be a string, got {type(code).__name__}")

    normalised = code.strip().upper()
    currency = CURRENCIES.get(normalised)
    if currency is None:
        raise UnsupportedCurrencyError(
            f"Unsupported currency code: {code!r}",
            context={"code": code, "supported": sorted(SUPPORTED_CURRENCY_CODES)},
        )
    return currency


def normalise_currency_code(code: str) -> str:
    """Return the canonical uppercase code, validating it is supported."""
    return get_currency(code).code
