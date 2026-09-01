"""Currency registry validation."""

from __future__ import annotations

import pytest

from app.core.errors import UnsupportedCurrencyError
from app.domain.currencies import (
    SUPPORTED_CURRENCY_CODES,
    get_currency,
    is_supported_currency,
    normalise_currency_code,
)


class TestLookup:
    def test_known_currency(self) -> None:
        assert get_currency("USD").name == "US Dollar"

    def test_lookup_is_case_insensitive_and_trims(self) -> None:
        assert get_currency("  gbp ").code == "GBP"

    def test_normalise_returns_canonical_code(self) -> None:
        assert normalise_currency_code("eur") == "EUR"

    def test_minor_unit_digits_vary_by_currency(self) -> None:
        assert get_currency("USD").minor_unit_digits == 2
        assert get_currency("JPY").minor_unit_digits == 0


class TestInvalidCurrency:
    @pytest.mark.parametrize("code", ["XXX", "ZZZ", "US", "USDD", "", "   ", "123"])
    def test_unsupported_codes_raise(self, code: str) -> None:
        with pytest.raises(UnsupportedCurrencyError):
            get_currency(code)

    def test_error_lists_supported_codes(self) -> None:
        """The message must be actionable, not just a rejection."""
        with pytest.raises(UnsupportedCurrencyError) as exc_info:
            get_currency("XBT")
        assert "USD" in exc_info.value.context["supported"]

    def test_never_silently_defaults(self) -> None:
        """Guessing the currency of a salary is worse than failing."""
        with pytest.raises(UnsupportedCurrencyError):
            get_currency("BTC")

    def test_is_supported_currency_predicate(self) -> None:
        assert is_supported_currency("USD")
        assert not is_supported_currency("XXX")
        assert not is_supported_currency("usd")  # predicate expects canonical form

    def test_registry_is_non_empty_and_uppercase(self) -> None:
        assert SUPPORTED_CURRENCY_CODES
        assert all(code.isupper() and len(code) == 3 for code in SUPPORTED_CURRENCY_CODES)
