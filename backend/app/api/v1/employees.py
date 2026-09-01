"""Employee routes.

Thin by design: parse, delegate, shape. No business logic here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import EmployeeServiceDep, PaginationDep
from app.domain.enums import EmploymentStatus
from app.repositories.employee import EmployeeFilters
from app.schemas.common import Page
from app.schemas.employee import EmployeeCreate, EmployeeDetail, EmployeeRead, EmployeeUpdate

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=Page[EmployeeRead], summary="List employees")
def list_employees(
    service: EmployeeServiceDep,
    pagination: PaginationDep,
    department: Annotated[str | None, Query()] = None,
    country_code: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    employment_status: Annotated[EmploymentStatus | None, Query(alias="status")] = None,
    manager_id: Annotated[int | None, Query(ge=1)] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[EmployeeRead]:
    filters = EmployeeFilters(
        department=department,
        country_code=country_code,
        status=employment_status,
        manager_id=manager_id,
        search=search,
    )
    employees, total = service.list(
        limit=pagination.limit, offset=pagination.offset, filters=filters
    )
    return Page[EmployeeRead](
        items=[EmployeeRead.model_validate(employee) for employee in employees],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post(
    "",
    response_model=EmployeeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an employee",
    responses={409: {"description": "Employee number or work email already in use"}},
)
def create_employee(payload: EmployeeCreate, service: EmployeeServiceDep) -> EmployeeRead:
    employee = service.create(payload)
    return EmployeeRead.model_validate(employee)


@router.get(
    "/{employee_id}",
    response_model=EmployeeDetail,
    summary="Get an employee with compensation history",
    responses={404: {"description": "Employee not found"}},
)
def get_employee(employee_id: int, service: EmployeeServiceDep) -> EmployeeDetail:
    return EmployeeDetail.from_model(service.get_detail(employee_id))


@router.patch(
    "/{employee_id}",
    response_model=EmployeeRead,
    summary="Update an employee",
    responses={404: {"description": "Employee not found"}},
)
def update_employee(
    employee_id: int, payload: EmployeeUpdate, service: EmployeeServiceDep
) -> EmployeeRead:
    return EmployeeRead.model_validate(service.update(employee_id, payload))
