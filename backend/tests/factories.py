"""Deterministic test data builders.

No randomness and no ambient clock: every value is either fixed or explicitly
passed, so a failing test fails the same way every run.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.domain.enums import PayPeriod, PayType, SalaryChangeReason
from app.schemas.employee import EmployeeCreate
from app.schemas.salary_record import SalaryRecordCreate

HIRE_DATE = date(2020, 1, 1)


def employee_payload(**overrides: Any) -> EmployeeCreate:
    data: dict[str, Any] = {
        "employee_number": "E-000001",
        "first_name": "Priya",
        "last_name": "Raman",
        "work_email": "priya.raman@acme.com",
        "job_title": "Senior Engineer",
        "department": "Engineering",
        "country_code": "GB",
        "hire_date": HIRE_DATE,
        "status": "active",
    }
    data.update(overrides)
    return EmployeeCreate.model_validate(data)


def salary_payload(**overrides: Any) -> SalaryRecordCreate:
    data: dict[str, Any] = {
        "amount_minor": 8_500_000,  # 85,000.00
        "currency_code": "GBP",
        "pay_type": PayType.BASE,
        "pay_period": PayPeriod.ANNUAL,
        "effective_from": HIRE_DATE,
        "change_reason": SalaryChangeReason.HIRE,
    }
    data.update(overrides)
    return SalaryRecordCreate.model_validate(data)


def employee_api_payload(**overrides: Any) -> dict[str, Any]:
    """The same employee data as a JSON-ready dict for API tests."""
    payload = employee_payload(**overrides)
    return payload.model_dump(mode="json")


def salary_api_payload(**overrides: Any) -> dict[str, Any]:
    payload = salary_payload(**overrides)
    return payload.model_dump(mode="json")
