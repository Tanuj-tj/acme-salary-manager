"""Employee persistence.

Query construction lives here so it can be tested in isolation and so services
stay readable. Nothing in this layer decides policy -- it answers questions and
stages writes; the service decides what that means and when to commit.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.domain.enums import EmploymentStatus
from app.models.employee import Employee


@dataclass(frozen=True, slots=True)
class EmployeeFilters:
    """Allowlisted list filters.

    A fixed set of typed fields rather than a generic filter expression: an
    open-ended filter language would be both a SQL injection surface and an
    unbounded-query surface.
    """

    department: str | None = None
    country_code: str | None = None
    status: EmploymentStatus | None = None
    manager_id: int | None = None
    search: str | None = None


class EmployeeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, employee_id: int) -> Employee | None:
        return self._session.get(Employee, employee_id)

    def get_with_salary_records(self, employee_id: int) -> Employee | None:
        """Load an employee and their history in two queries, never N+1."""
        stmt = (
            select(Employee)
            .where(Employee.id == employee_id)
            .options(selectinload(Employee.salary_records))
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_employee_number(self, employee_number: str) -> Employee | None:
        stmt = select(Employee).where(Employee.employee_number == employee_number)
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_work_email(self, work_email: str) -> Employee | None:
        stmt = select(Employee).where(Employee.work_email == work_email.lower())
        return self._session.execute(stmt).scalar_one_or_none()

    def list_page(
        self,
        *,
        limit: int,
        offset: int,
        filters: EmployeeFilters | None = None,
    ) -> tuple[Sequence[Employee], int]:
        """Return one page of employees plus the total matching count."""
        filters = filters or EmployeeFilters()

        stmt = self._apply_filters(select(Employee), filters)
        total = self._session.execute(
            self._apply_filters(select(func.count(Employee.id)), filters)
        ).scalar_one()

        page_stmt = stmt.order_by(Employee.last_name, Employee.first_name, Employee.id)
        items = self._session.execute(page_stmt.limit(limit).offset(offset)).scalars().all()
        return items, total

    def add(self, employee: Employee) -> Employee:
        self._session.add(employee)
        self._session.flush()
        return employee

    @staticmethod
    def _apply_filters(stmt: Select[Any], filters: EmployeeFilters) -> Select[Any]:
        if filters.department is not None:
            stmt = stmt.where(Employee.department == filters.department)
        if filters.country_code is not None:
            stmt = stmt.where(Employee.country_code == filters.country_code.upper())
        if filters.status is not None:
            stmt = stmt.where(Employee.status == filters.status)
        if filters.manager_id is not None:
            stmt = stmt.where(Employee.manager_id == filters.manager_id)
        if filters.search:
            pattern = f"%{filters.search.strip()}%"
            stmt = stmt.where(
                or_(
                    Employee.first_name.ilike(pattern),
                    Employee.last_name.ilike(pattern),
                    Employee.employee_number.ilike(pattern),
                    Employee.work_email.ilike(pattern),
                )
            )
        return stmt
