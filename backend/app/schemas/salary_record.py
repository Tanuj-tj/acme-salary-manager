"""SalaryRecord API contracts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Self

from pydantic import Field, field_validator, model_validator

from app.domain.enums import PayPeriod, PayType, SalaryChangeReason
from app.models.salary_record import SalaryRecord
from app.schemas.common import ApiModel, CurrencyCode, MoneyRead, validate_currency_code


class SalaryRecordCreate(ApiModel):
    """Request to record a compensation amount effective from a given date.

    The amount is given in **integer minor units** (cents, pence, yen) rather
    than a decimal. This is exact by construction and removes any question of
    how the server rounds a submitted fractional value.
    """

    amount_minor: int = Field(
        gt=0,
        description="Amount in integer minor units, e.g. 8500000 = 85,000.00 USD",
        examples=[8500000],
    )
    currency_code: CurrencyCode
    pay_type: PayType = PayType.BASE
    pay_period: PayPeriod = PayPeriod.ANNUAL
    effective_from: date
    effective_to: date | None = None
    change_reason: SalaryChangeReason = SalaryChangeReason.OTHER
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("currency_code")
    @classmethod
    def _validate_currency(cls, value: str) -> str:
        return validate_currency_code(value)

    @model_validator(mode="after")
    def _check_period(self) -> Self:
        # Mirrors app.domain.effective_dating.validate_period, so a malformed
        # period is a 422 on the request rather than reaching the service.
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        return self


class SalaryRecordRead(ApiModel):
    id: int
    employee_id: int
    amount: MoneyRead
    pay_type: PayType
    pay_period: PayPeriod
    effective_from: date
    effective_to: date | None
    is_open_ended: bool
    change_reason: SalaryChangeReason
    note: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, record: SalaryRecord) -> Self:
        return cls(
            id=record.id,
            employee_id=record.employee_id,
            amount=MoneyRead.from_money(record.amount),
            pay_type=record.pay_type,
            pay_period=record.pay_period,
            effective_from=record.effective_from,
            effective_to=record.effective_to,
            is_open_ended=record.is_open_ended,
            change_reason=record.change_reason,
            note=record.note,
            created_at=record.created_at,
        )
