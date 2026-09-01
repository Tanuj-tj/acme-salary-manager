"""Employee API contracts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Self

from pydantic import EmailStr, Field, field_validator, model_validator

from app.domain.enums import EmploymentStatus
from app.models.employee import Employee
from app.schemas.common import ApiModel
from app.schemas.salary_record import SalaryRecordRead

EmployeeNumber = Annotated[
    str, Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9._-]+$", examples=["E-001234"])
]
CountryCode = Annotated[
    str, Field(min_length=2, max_length=2, description="ISO 3166-1 alpha-2", examples=["GB"])
]


class EmployeeBase(ApiModel):
    employee_number: EmployeeNumber
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    work_email: EmailStr
    job_title: str = Field(min_length=1, max_length=120)
    department: str = Field(min_length=1, max_length=120)
    country_code: CountryCode
    hire_date: date
    termination_date: date | None = None
    status: EmploymentStatus = EmploymentStatus.ACTIVE
    manager_id: int | None = None

    @field_validator("country_code")
    @classmethod
    def _normalise_country(cls, value: str) -> str:
        code = value.strip().upper()
        if not code.isalpha():
            raise ValueError(f"Country code must be two letters, got {value!r}")
        return code

    @field_validator("work_email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def _check_employment_dates(self) -> Self:
        if self.termination_date is not None and self.termination_date < self.hire_date:
            raise ValueError("termination_date cannot precede hire_date")
        return self


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(ApiModel):
    """Partial update. Every field optional; unset fields are left untouched."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    work_email: EmailStr | None = None
    job_title: str | None = Field(default=None, min_length=1, max_length=120)
    department: str | None = Field(default=None, min_length=1, max_length=120)
    country_code: CountryCode | None = None
    termination_date: date | None = None
    status: EmploymentStatus | None = None
    manager_id: int | None = None

    @field_validator("country_code")
    @classmethod
    def _normalise_country(cls, value: str | None) -> str | None:
        if value is None:
            return None
        code = value.strip().upper()
        if not code.isalpha():
            raise ValueError(f"Country code must be two letters, got {value!r}")
        return code


class EmployeeRead(ApiModel):
    id: int
    employee_number: str
    first_name: str
    last_name: str
    full_name: str
    work_email: str
    job_title: str
    department: str
    country_code: str
    hire_date: date
    termination_date: date | None
    status: EmploymentStatus
    manager_id: int | None
    created_at: datetime
    updated_at: datetime


class EmployeeDetail(EmployeeRead):
    """Employee with their full compensation history, newest first."""

    salary_records: list[SalaryRecordRead]

    @classmethod
    def from_model(cls, employee: Employee) -> Self:
        return cls(
            id=employee.id,
            employee_number=employee.employee_number,
            first_name=employee.first_name,
            last_name=employee.last_name,
            full_name=employee.full_name,
            work_email=employee.work_email,
            job_title=employee.job_title,
            department=employee.department,
            country_code=employee.country_code,
            hire_date=employee.hire_date,
            termination_date=employee.termination_date,
            status=employee.status,
            manager_id=employee.manager_id,
            created_at=employee.created_at,
            updated_at=employee.updated_at,
            salary_records=[
                SalaryRecordRead.from_model(record) for record in employee.salary_records
            ],
        )
