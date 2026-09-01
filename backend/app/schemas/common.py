"""Shared API schema building blocks."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Generic, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.currencies import SUPPORTED_CURRENCY_CODES, is_supported_currency
from app.domain.money import Money

ItemT = TypeVar("ItemT")


class ApiModel(BaseModel):
    """Base for every request and response schema."""

    model_config = ConfigDict(from_attributes=True, extra="forbid", str_strip_whitespace=True)


CurrencyCode = Annotated[
    str,
    Field(
        min_length=3,
        max_length=3,
        description=f"ISO 4217 code. Supported: {', '.join(sorted(SUPPORTED_CURRENCY_CODES))}",
        examples=["USD"],
    ),
]


def validate_currency_code(value: str) -> str:
    """Normalise to uppercase and reject unsupported codes.

    Shared by every schema carrying a currency so the rule cannot drift between
    endpoints.
    """
    code = value.strip().upper()
    if not is_supported_currency(code):
        raise ValueError(
            f"Unsupported currency code {value!r}. "
            f"Supported: {', '.join(sorted(SUPPORTED_CURRENCY_CODES))}"
        )
    return code


class MoneyRead(ApiModel):
    """Money on the wire.

    Both representations are sent: ``amount_minor`` is the exact integer the
    client should compute with, ``amount`` is the human-readable major-unit
    value. ``minor_unit_digits`` is included so clients can format correctly
    without hardcoding 2 (JPY has 0).
    """

    amount_minor: int
    currency_code: str
    amount: Decimal
    minor_unit_digits: int

    @classmethod
    def from_money(cls, money: Money) -> Self:
        return cls(
            amount_minor=money.amount_minor,
            currency_code=money.currency_code,
            amount=money.to_major(),
            minor_unit_digits=money.currency.minor_unit_digits,
        )


class Page(ApiModel, Generic[ItemT]):
    """Paginated envelope.

    Every list endpoint returns this; no endpoint returns a bare array. With
    10,000 employees an unbounded list response is a real hazard, and a
    consistent envelope makes the cap visible to clients.
    """

    items: list[ItemT]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class HealthResponse(ApiModel):
    status: str
    environment: str
    version: str


class ReadinessResponse(ApiModel):
    status: str
    database: str


class ProblemDetail(ApiModel):
    """RFC 7807 problem details.

    ``type`` is a stable machine-readable slug so clients branch on failure
    mode rather than parsing prose.
    """

    model_config = ConfigDict(extra="allow")

    type: str
    title: str
    status: int
    detail: str
    instance: str | None = None

    @field_validator("type")
    @classmethod
    def _prefix_type(cls, value: str) -> str:
        return value if value.startswith(("http://", "https://", "/")) else f"/errors/{value}"
