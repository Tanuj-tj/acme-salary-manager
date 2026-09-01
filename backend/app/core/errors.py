"""Application error hierarchy.

Deliberately free of framework imports: domain and service code raises these,
and only ``app.api.error_handlers`` knows how to turn them into HTTP responses.
Each error carries the status code and stable machine-readable ``error_type``
that the RFC 7807 response is built from, so clients can branch on failure mode
without string-matching human-readable messages.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for all expected, handled application errors."""

    status_code: int = 500
    error_type: str = "internal-error"
    title: str = "Internal Server Error"

    def __init__(self, detail: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.context = context or {}


class NotFoundError(AppError):
    status_code = 404
    error_type = "not-found"
    title = "Resource Not Found"


class ConflictError(AppError):
    """The request is well-formed but conflicts with existing state."""

    status_code = 409
    error_type = "conflict"
    title = "Conflict"


class DomainValidationError(AppError):
    """A business rule was violated.

    Distinct from Pydantic's request-shape validation: the payload parsed fine,
    but the values are not valid for the domain.
    """

    status_code = 422
    error_type = "domain-validation-error"
    title = "Domain Validation Error"


class UnsupportedCurrencyError(DomainValidationError):
    error_type = "unsupported-currency"
    title = "Unsupported Currency"


class CurrencyMismatchError(DomainValidationError):
    """Raised when two Money values in different currencies are combined.

    Never caught and coerced: silently converting is how cross-currency totals
    become quietly wrong.
    """

    error_type = "currency-mismatch"
    title = "Currency Mismatch"


class InvalidSalaryAmountError(DomainValidationError):
    error_type = "invalid-salary-amount"
    title = "Invalid Salary Amount"


class InvalidEffectivePeriodError(DomainValidationError):
    error_type = "invalid-effective-period"
    title = "Invalid Effective Period"


class OverlappingSalaryPeriodError(ConflictError):
    error_type = "overlapping-salary-period"
    title = "Overlapping Salary Period"


class DuplicateEmployeeError(ConflictError):
    error_type = "duplicate-employee"
    title = "Duplicate Employee"
