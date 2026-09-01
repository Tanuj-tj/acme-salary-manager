"""Salary record business logic.

The rules that make compensation history trustworthy live here: amounts are
valid money, periods are well-formed, periods never overlap, and recording a
raise closes the record it supersedes rather than leaving two open.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.errors import (
    DomainValidationError,
    NotFoundError,
    OverlappingSalaryPeriodError,
)
from app.domain.effective_dating import validate_period
from app.domain.enums import PayType
from app.domain.money import Money
from app.domain.salary_rules import validate_salary_amount
from app.models.employee import Employee
from app.models.salary_record import SalaryRecord
from app.repositories.employee import EmployeeRepository
from app.repositories.salary_record import SalaryRecordRepository
from app.schemas.salary_record import SalaryRecordCreate


class SalaryRecordService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._records = SalaryRecordRepository(session)
        self._employees = EmployeeRepository(session)

    def list_for_employee(
        self, employee_id: int, *, pay_type: PayType | None = None
    ) -> Sequence[SalaryRecord]:
        self._require_employee(employee_id)
        return self._records.list_for_employee(employee_id, pay_type=pay_type)

    def create_for_employee(self, employee_id: int, payload: SalaryRecordCreate) -> SalaryRecord:
        employee = self._require_employee(employee_id)

        # Money.of validates the currency code and rejects non-integer amounts;
        # an unsupported currency never reaches the database.
        amount = Money.of(payload.amount_minor, payload.currency_code)
        validate_salary_amount(amount)
        validate_period(payload.effective_from, payload.effective_to)
        self._assert_not_before_hire(employee, payload)

        # Identify the record this one supersedes, but do not modify it yet:
        # validation must be able to fail without leaving the session dirty.
        superseded = self._find_superseded_record(employee_id, payload)

        overlapping = self._records.find_overlapping(
            employee_id=employee_id,
            pay_type=payload.pay_type,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            # Once closed at the new start date the superseded record abuts
            # rather than overlaps, so it is not a genuine conflict.
            exclude_id=superseded.id if superseded is not None else None,
        )
        if overlapping:
            clash = overlapping[0]
            raise OverlappingSalaryPeriodError(
                f"A {payload.pay_type.value} salary record already covers part of "
                f"{payload.effective_from.isoformat()} onwards "
                f"(record {clash.id}: {clash.effective_from.isoformat()} to "
                f"{clash.effective_to.isoformat() if clash.effective_to else 'open'})",
                context={"conflicting_record_id": clash.id},
            )

        if superseded is not None:
            superseded.effective_to = payload.effective_from
            self._session.flush()

        record = SalaryRecord(
            employee_id=employee_id,
            amount_minor=amount.amount_minor,
            currency_code=amount.currency_code,
            pay_type=payload.pay_type,
            pay_period=payload.pay_period,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            change_reason=payload.change_reason,
            note=payload.note,
        )
        self._records.add(record)
        self._session.commit()
        return record

    # -- internals ------------------------------------------------------

    def _require_employee(self, employee_id: int) -> Employee:
        employee = self._employees.get(employee_id)
        if employee is None:
            raise NotFoundError(f"Employee {employee_id} not found")
        return employee

    @staticmethod
    def _assert_not_before_hire(employee: Employee, payload: SalaryRecordCreate) -> None:
        """Reject compensation effective before the employee was hired.

        A data-quality guard: it is almost always a mistyped year, and it would
        silently corrupt any point-in-time payroll figure covering that date.
        """
        if payload.effective_from < employee.hire_date:
            raise DomainValidationError(
                f"effective_from ({payload.effective_from.isoformat()}) precedes the "
                f"employee's hire date ({employee.hire_date.isoformat()})",
                context={
                    "effective_from": payload.effective_from.isoformat(),
                    "hire_date": employee.hire_date.isoformat(),
                },
            )

    def _find_superseded_record(
        self, employee_id: int, payload: SalaryRecordCreate
    ) -> SalaryRecord | None:
        """Return the open record this payload supersedes, if any.

        This is the ordinary "give someone a raise" path: the previous record
        stops being in effect on the day the new one starts. Half-open
        intervals mean the two abut exactly, with no gap and no double count.

        Only an open record starting strictly earlier qualifies. Anything else
        is a genuine conflict, left for the overlap check to reject.
        """
        open_record = self._records.get_open_record(employee_id, payload.pay_type)
        if open_record is None or open_record.effective_from >= payload.effective_from:
            return None
        return open_record
