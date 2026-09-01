"""Shared FastAPI dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.services.employee import EmployeeService
from app.services.salary_record import SalaryRecordService

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@dataclass(frozen=True, slots=True)
class Pagination:
    limit: int
    offset: int


def get_pagination(
    limit: Annotated[
        int,
        Query(ge=1, le=200, description="Maximum items to return (hard cap 200)"),
    ] = 50,
    offset: Annotated[int, Query(ge=0, description="Items to skip")] = 0,
) -> Pagination:
    """Offset pagination with a hard cap.

    The cap is not negotiable by the client: an uncapped list endpoint over
    10,000 employees is the easiest way to take the service down.
    """
    return Pagination(limit=limit, offset=offset)


PaginationDep = Annotated[Pagination, Depends(get_pagination)]


def get_employee_service(session: SessionDep) -> EmployeeService:
    return EmployeeService(session)


def get_salary_record_service(session: SessionDep) -> SalaryRecordService:
    return SalaryRecordService(session)


EmployeeServiceDep = Annotated[EmployeeService, Depends(get_employee_service)]
SalaryRecordServiceDep = Annotated[SalaryRecordService, Depends(get_salary_record_service)]
