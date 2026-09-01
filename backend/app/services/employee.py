"""Employee business logic.

Owns the rules and the transaction boundary. Route handlers call into here and
do nothing else of substance.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.errors import DuplicateEmployeeError, NotFoundError
from app.models.employee import Employee
from app.repositories.employee import EmployeeFilters, EmployeeRepository
from app.schemas.employee import EmployeeCreate, EmployeeUpdate


class EmployeeService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._employees = EmployeeRepository(session)

    def create(self, payload: EmployeeCreate) -> Employee:
        self._assert_unique(payload.employee_number, payload.work_email)
        if payload.manager_id is not None:
            self._require(payload.manager_id, what="Manager")

        employee = Employee(
            employee_number=payload.employee_number,
            first_name=payload.first_name,
            last_name=payload.last_name,
            work_email=payload.work_email,
            job_title=payload.job_title,
            department=payload.department,
            country_code=payload.country_code,
            hire_date=payload.hire_date,
            termination_date=payload.termination_date,
            status=payload.status,
            manager_id=payload.manager_id,
        )
        self._employees.add(employee)
        self._session.commit()
        return employee

    def get(self, employee_id: int) -> Employee:
        return self._require(employee_id)

    def get_detail(self, employee_id: int) -> Employee:
        employee = self._employees.get_with_salary_records(employee_id)
        if employee is None:
            raise NotFoundError(f"Employee {employee_id} not found")
        return employee

    def list(
        self, *, limit: int, offset: int, filters: EmployeeFilters | None = None
    ) -> tuple[Sequence[Employee], int]:
        return self._employees.list_page(limit=limit, offset=offset, filters=filters)

    def update(self, employee_id: int, payload: EmployeeUpdate) -> Employee:
        employee = self._require(employee_id)
        changes = payload.model_dump(exclude_unset=True)

        if "work_email" in changes:
            existing = self._employees.get_by_work_email(changes["work_email"])
            if existing is not None and existing.id != employee_id:
                raise DuplicateEmployeeError(
                    f"Work email {changes['work_email']!r} is already in use"
                )

        manager_id = changes.get("manager_id")
        if manager_id is not None:
            if manager_id == employee_id:
                raise DuplicateEmployeeError("An employee cannot be their own manager")
            self._require(manager_id, what="Manager")

        for field, value in changes.items():
            setattr(employee, field, value)

        self._session.flush()
        self._session.commit()
        return employee

    # -- internals ------------------------------------------------------

    def _require(self, employee_id: int, *, what: str = "Employee") -> Employee:
        employee = self._employees.get(employee_id)
        if employee is None:
            raise NotFoundError(f"{what} {employee_id} not found")
        return employee

    def _assert_unique(self, employee_number: str, work_email: str) -> None:
        """Check uniqueness up front to return a clear 409.

        The unique indexes remain the real guarantee against races; this exists
        so the common case gets a useful message rather than an integrity error.
        """
        if self._employees.get_by_employee_number(employee_number) is not None:
            raise DuplicateEmployeeError(
                f"Employee number {employee_number!r} is already in use",
                context={"employee_number": employee_number},
            )
        if self._employees.get_by_work_email(work_email) is not None:
            raise DuplicateEmployeeError(
                f"Work email {work_email!r} is already in use",
                context={"work_email": work_email},
            )
