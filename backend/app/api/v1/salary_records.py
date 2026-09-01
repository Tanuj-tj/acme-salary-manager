"""Salary record routes, nested under the employee that owns them."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import SalaryRecordServiceDep
from app.domain.enums import PayType
from app.schemas.salary_record import SalaryRecordCreate, SalaryRecordRead

router = APIRouter(prefix="/employees/{employee_id}/salary-records", tags=["salary-records"])


@router.get(
    "",
    response_model=list[SalaryRecordRead],
    summary="List an employee's salary history",
    responses={404: {"description": "Employee not found"}},
)
def list_salary_records(
    employee_id: int,
    service: SalaryRecordServiceDep,
    pay_type: Annotated[PayType | None, Query()] = None,
) -> list[SalaryRecordRead]:
    """Full history, newest effective date first.

    Not paginated: a single employee's compensation history is bounded by their
    tenure, so it is tens of rows at most.
    """
    records = service.list_for_employee(employee_id, pay_type=pay_type)
    return [SalaryRecordRead.from_model(record) for record in records]


@router.post(
    "",
    response_model=SalaryRecordRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a salary change",
    responses={
        404: {"description": "Employee not found"},
        409: {"description": "The period overlaps an existing record"},
        422: {"description": "Invalid amount, currency, or effective period"},
    },
)
def create_salary_record(
    employee_id: int, payload: SalaryRecordCreate, service: SalaryRecordServiceDep
) -> SalaryRecordRead:
    """Create a record, closing the one it supersedes.

    Posting an open-ended record that starts later than the current one is the
    ordinary raise path: the previous record is closed on the new start date.
    """
    record = service.create_for_employee(employee_id, payload)
    return SalaryRecordRead.from_model(record)
