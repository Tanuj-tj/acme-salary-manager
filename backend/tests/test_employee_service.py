"""Employee creation and update rules."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors import DuplicateEmployeeError, NotFoundError
from app.domain.enums import EmploymentStatus
from app.repositories.employee import EmployeeFilters
from app.schemas.employee import EmployeeUpdate
from app.services.employee import EmployeeService
from tests.factories import employee_payload


class TestEmployeeCreation:
    def test_creates_employee_with_expected_fields(self, session: Session) -> None:
        service = EmployeeService(session)

        employee = service.create(employee_payload())

        assert employee.id is not None
        assert employee.employee_number == "E-000001"
        assert employee.full_name == "Priya Raman"
        assert employee.country_code == "GB"
        assert employee.status is EmploymentStatus.ACTIVE
        assert employee.created_at is not None

    def test_employee_has_no_salary_on_creation(self, session: Session) -> None:
        """Compensation is history, not a field. A new employee starts empty."""
        employee = EmployeeService(session).create(employee_payload())
        assert employee.salary_records == []

    def test_work_email_is_normalised_to_lowercase(self, session: Session) -> None:
        employee = EmployeeService(session).create(
            employee_payload(work_email="Priya.Raman@ACME.com")
        )
        assert employee.work_email == "priya.raman@acme.com"

    def test_country_code_is_normalised_to_uppercase(self, session: Session) -> None:
        employee = EmployeeService(session).create(employee_payload(country_code="gb"))
        assert employee.country_code == "GB"

    def test_duplicate_employee_number_is_rejected(self, session: Session) -> None:
        service = EmployeeService(session)
        service.create(employee_payload())

        with pytest.raises(DuplicateEmployeeError, match=r"[Ee]mployee number"):
            service.create(employee_payload(work_email="other@acme.com"))

    def test_duplicate_work_email_is_rejected(self, session: Session) -> None:
        service = EmployeeService(session)
        service.create(employee_payload())

        with pytest.raises(DuplicateEmployeeError, match=r"[Ww]ork email"):
            service.create(employee_payload(employee_number="E-000002"))

    def test_manager_must_exist(self, session: Session) -> None:
        with pytest.raises(NotFoundError, match="Manager"):
            EmployeeService(session).create(employee_payload(manager_id=999))

    def test_employee_can_be_assigned_an_existing_manager(self, session: Session) -> None:
        service = EmployeeService(session)
        manager = service.create(employee_payload())

        report = service.create(
            employee_payload(
                employee_number="E-000002",
                work_email="sam.okafor@acme.com",
                first_name="Sam",
                last_name="Okafor",
                manager_id=manager.id,
            )
        )

        assert report.manager_id == manager.id
        assert report.manager is not None
        assert report.manager.full_name == "Priya Raman"
        assert [r.id for r in manager.direct_reports] == [report.id]


class TestEmployeeValidation:
    def test_termination_before_hire_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="termination_date"):
            employee_payload(termination_date=date(2019, 1, 1))

    def test_invalid_country_code_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            employee_payload(country_code="G1")

    def test_invalid_email_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            employee_payload(work_email="not-an-email")

    def test_blank_first_name_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            employee_payload(first_name="")

    def test_unknown_field_is_rejected(self) -> None:
        """extra='forbid' stops a typo'd field being silently ignored."""
        with pytest.raises(ValidationError):
            employee_payload(salary=100000)


class TestEmployeeLookupAndUpdate:
    def test_get_missing_employee_raises_not_found(self, session: Session) -> None:
        with pytest.raises(NotFoundError):
            EmployeeService(session).get(12345)

    def test_update_applies_only_provided_fields(self, session: Session) -> None:
        service = EmployeeService(session)
        employee = service.create(employee_payload())

        updated = service.update(employee.id, EmployeeUpdate(department="Product"))

        assert updated.department == "Product"
        assert updated.job_title == "Senior Engineer"

    def test_employee_cannot_manage_themselves(self, session: Session) -> None:
        service = EmployeeService(session)
        employee = service.create(employee_payload())

        with pytest.raises(DuplicateEmployeeError, match="own manager"):
            service.update(employee.id, EmployeeUpdate(manager_id=employee.id))

    def test_list_filters_by_department(self, session: Session) -> None:
        service = EmployeeService(session)
        service.create(employee_payload())
        service.create(
            employee_payload(
                employee_number="E-000002",
                work_email="sam@acme.com",
                department="Product",
            )
        )

        items, total = service.list(
            limit=50, offset=0, filters=EmployeeFilters(department="Product")
        )

        assert total == 1
        assert items[0].department == "Product"

    def test_list_paginates(self, session: Session) -> None:
        service = EmployeeService(session)
        for index in range(5):
            service.create(
                employee_payload(
                    employee_number=f"E-00000{index}",
                    work_email=f"user{index}@acme.com",
                    last_name=f"Name{index}",
                )
            )

        items, total = service.list(limit=2, offset=0)

        assert total == 5
        assert len(items) == 2
