"""SalaryRecord persistence."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import and_, or_, select, true
from sqlalchemy.orm import Session

from app.domain.enums import PayType
from app.models.salary_record import SalaryRecord


class SalaryRecordRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, record_id: int) -> SalaryRecord | None:
        return self._session.get(SalaryRecord, record_id)

    def list_for_employee(
        self, employee_id: int, *, pay_type: PayType | None = None
    ) -> Sequence[SalaryRecord]:
        """Full history for an employee, newest effective date first."""
        stmt = select(SalaryRecord).where(SalaryRecord.employee_id == employee_id)
        if pay_type is not None:
            stmt = stmt.where(SalaryRecord.pay_type == pay_type)
        stmt = stmt.order_by(SalaryRecord.effective_from.desc(), SalaryRecord.id.desc())
        return self._session.execute(stmt).scalars().all()

    def get_open_record(self, employee_id: int, pay_type: PayType) -> SalaryRecord | None:
        """The currently-in-effect record, if any.

        At most one can exist per (employee, pay_type) -- guaranteed by the
        partial unique index on the table.
        """
        stmt = select(SalaryRecord).where(
            SalaryRecord.employee_id == employee_id,
            SalaryRecord.pay_type == pay_type,
            SalaryRecord.effective_to.is_(None),
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def find_overlapping(
        self,
        *,
        employee_id: int,
        pay_type: PayType,
        effective_from: date,
        effective_to: date | None,
        exclude_id: int | None = None,
    ) -> Sequence[SalaryRecord]:
        """Records of the same pay type whose period intersects the given one.

        Half-open semantics: two periods overlap unless one ends on or before
        the other begins. Expressed in SQL so the check is a single query
        rather than loading a history and scanning it in Python.
        """
        # existing.to IS NULL OR existing.to > new.from
        existing_ends_after_new_starts = or_(
            SalaryRecord.effective_to.is_(None),
            SalaryRecord.effective_to > effective_from,
        )
        # new.to IS NULL OR existing.from < new.to
        new_ends_after_existing_starts = (
            true() if effective_to is None else SalaryRecord.effective_from < effective_to
        )

        stmt = select(SalaryRecord).where(
            SalaryRecord.employee_id == employee_id,
            SalaryRecord.pay_type == pay_type,
            and_(existing_ends_after_new_starts, new_ends_after_existing_starts),
        )
        if exclude_id is not None:
            stmt = stmt.where(SalaryRecord.id != exclude_id)
        return self._session.execute(stmt).scalars().all()

    def add(self, record: SalaryRecord) -> SalaryRecord:
        self._session.add(record)
        self._session.flush()
        return record
