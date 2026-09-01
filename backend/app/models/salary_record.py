"""SalaryRecord ORM model.

One row is one compensation element, valid over a half-open date interval.
An employee's "current salary" is derived by resolving which record is in
effect today, never by reading a mutable column.
"""

from __future__ import annotations

import enum
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.domain.enums import PayPeriod, PayType, SalaryChangeReason
from app.domain.money import Money

if TYPE_CHECKING:
    from app.models.employee import Employee


def _enum_column(enum_cls: type[enum.Enum], length: int) -> Enum:
    """Portable enum column: VARCHAR + CHECK, never a native database ENUM."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda cls: [member.value for member in cls],
        validate_strings=True,
    )


class SalaryRecord(TimestampMixin, Base):
    __tablename__ = "salary_records"

    id: Mapped[int] = mapped_column(primary_key=True)

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True
    )

    # Integer minor units, never a float. Paired with its currency code; the two
    # are only ever read together, via the `amount` property.
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency_code: Mapped[str] = mapped_column(String(3))

    pay_type: Mapped[PayType] = mapped_column(_enum_column(PayType, 20), default=PayType.BASE)
    pay_period: Mapped[PayPeriod] = mapped_column(
        _enum_column(PayPeriod, 20), default=PayPeriod.ANNUAL
    )

    effective_from: Mapped[date] = mapped_column(Date)
    # NULL means "currently in effect". At most one open record is permitted per
    # (employee, pay_type), enforced by the partial unique index below.
    effective_to: Mapped[date | None] = mapped_column(Date, default=None)

    change_reason: Mapped[SalaryChangeReason] = mapped_column(
        _enum_column(SalaryChangeReason, 30), default=SalaryChangeReason.OTHER
    )
    note: Mapped[str | None] = mapped_column(Text, default=None)

    employee: Mapped[Employee] = relationship(back_populates="salary_records")

    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="amount_is_positive"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="effective_period_is_valid",
        ),
        CheckConstraint("length(currency_code) = 3", name="currency_code_is_iso4217"),
        Index("ix_salary_records_employee_effective", "employee_id", "effective_from"),
        Index("ix_salary_records_effective_range", "effective_from", "effective_to"),
        # "At most one open record per (employee, pay_type)" enforced by the
        # database, not just by service code a future bug could bypass. Partial
        # indexes work on both SQLite (>= 3.8) and PostgreSQL; the dialect
        # kwargs are how SQLAlchemy emits the right DDL for each.
        Index(
            "uq_salary_records_open_period",
            "employee_id",
            "pay_type",
            unique=True,
            sqlite_where=text("effective_to IS NULL"),
            postgresql_where=text("effective_to IS NULL"),
        ),
    )

    @property
    def amount(self) -> Money:
        """The record's value as a Money object."""
        return Money.of(self.amount_minor, self.currency_code)

    @property
    def is_open_ended(self) -> bool:
        return self.effective_to is None

    def __repr__(self) -> str:
        return (
            f"<SalaryRecord id={self.id} employee_id={self.employee_id} "
            f"{self.amount_minor} {self.currency_code} from={self.effective_from}>"
        )
