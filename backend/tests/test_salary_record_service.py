"""Salary record creation, validation, and the employee relationship."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import (
    DomainValidationError,
    InvalidSalaryAmountError,
    NotFoundError,
    OverlappingSalaryPeriodError,
    UnsupportedCurrencyError,
)
from app.domain.enums import PayType, SalaryChangeReason
from app.models.employee import Employee
from app.models.salary_record import SalaryRecord
from app.services.employee import EmployeeService
from app.services.salary_record import SalaryRecordService
from tests.factories import HIRE_DATE, employee_payload, salary_payload


@pytest.fixture
def employee(session: Session) -> Employee:
    return EmployeeService(session).create(employee_payload())


@pytest.fixture
def service(session: Session) -> SalaryRecordService:
    return SalaryRecordService(session)


class TestSalaryRecordCreation:
    def test_creates_record_with_expected_fields(
        self, service: SalaryRecordService, employee: Employee
    ) -> None:
        record = service.create_for_employee(employee.id, salary_payload())

        assert record.id is not None
        assert record.employee_id == employee.id
        assert record.amount_minor == 8_500_000
        assert record.currency_code == "GBP"
        assert record.pay_type is PayType.BASE
        assert record.change_reason is SalaryChangeReason.HIRE
        assert record.effective_from == HIRE_DATE

    def test_new_record_is_open_ended_by_default(
        self, service: SalaryRecordService, employee: Employee
    ) -> None:
        record = service.create_for_employee(employee.id, salary_payload())
        assert record.effective_to is None
        assert record.is_open_ended

    def test_amount_is_exposed_as_money(
        self, service: SalaryRecordService, employee: Employee
    ) -> None:
        record = service.create_for_employee(employee.id, salary_payload())
        assert record.amount.to_major() == Decimal("85000.00")
        assert record.amount.currency_code == "GBP"

    def test_currency_code_is_normalised_to_uppercase(
        self, service: SalaryRecordService, employee: Employee
    ) -> None:
        record = service.create_for_employee(employee.id, salary_payload(currency_code="gbp"))
        assert record.currency_code == "GBP"

    def test_zero_minor_unit_currency_is_stored_exactly(
        self, session: Session, service: SalaryRecordService
    ) -> None:
        """JPY has no minor unit; 9,500,000 yen is 9,500,000 minor units."""
        employee = EmployeeService(session).create(
            employee_payload(
                employee_number="E-JP-01", work_email="kenji@acme.com", country_code="JP"
            )
        )
        record = service.create_for_employee(
            employee.id, salary_payload(amount_minor=9_500_000, currency_code="JPY")
        )
        assert record.amount.to_major() == Decimal("9500000")

    def test_record_for_unknown_employee_raises_not_found(
        self, service: SalaryRecordService
    ) -> None:
        with pytest.raises(NotFoundError, match="Employee"):
            service.create_for_employee(9999, salary_payload())


class TestEmployeeToSalaryRelationship:
    def test_records_are_reachable_from_the_employee(
        self, session: Session, service: SalaryRecordService, employee: Employee
    ) -> None:
        service.create_for_employee(employee.id, salary_payload())
        session.refresh(employee)

        assert len(employee.salary_records) == 1
        assert employee.salary_records[0].amount_minor == 8_500_000

    def test_employee_is_reachable_from_the_record(
        self, service: SalaryRecordService, employee: Employee
    ) -> None:
        record = service.create_for_employee(employee.id, salary_payload())
        assert record.employee.id == employee.id
        assert record.employee.full_name == "Priya Raman"

    def test_history_is_ordered_newest_first(
        self, session: Session, service: SalaryRecordService, employee: Employee
    ) -> None:
        service.create_for_employee(employee.id, salary_payload())
        service.create_for_employee(
            employee.id,
            salary_payload(
                amount_minor=9_200_000,
                effective_from=date(2022, 4, 1),
                change_reason=SalaryChangeReason.MERIT,
            ),
        )
        session.refresh(employee)

        assert [r.effective_from for r in employee.salary_records] == [
            date(2022, 4, 1),
            HIRE_DATE,
        ]

    def test_deleting_an_employee_cascades_to_their_records(
        self, session: Session, service: SalaryRecordService, employee: Employee
    ) -> None:
        service.create_for_employee(employee.id, salary_payload())
        employee_id = employee.id

        session.delete(employee)
        session.commit()

        remaining = (
            session.execute(select(SalaryRecord).where(SalaryRecord.employee_id == employee_id))
            .scalars()
            .all()
        )
        assert remaining == []

    def test_listing_records_for_unknown_employee_raises(
        self, service: SalaryRecordService
    ) -> None:
        with pytest.raises(NotFoundError):
            service.list_for_employee(4242)


class TestInvalidSalaryValues:
    @pytest.mark.parametrize("amount_minor", [0, -1, -8_500_000])
    def test_non_positive_amounts_are_rejected_by_the_schema(self, amount_minor: int) -> None:
        with pytest.raises(ValidationError):
            salary_payload(amount_minor=amount_minor)

    @pytest.mark.parametrize("amount_minor", [0, -8_500_000])
    def test_non_positive_amounts_are_rejected_by_the_service(
        self, service: SalaryRecordService, employee: Employee, amount_minor: int
    ) -> None:
        """Defence in depth: the rule holds even if the schema is bypassed."""
        payload = salary_payload().model_copy(update={"amount_minor": amount_minor})

        with pytest.raises(InvalidSalaryAmountError):
            service.create_for_employee(employee.id, payload)

    def test_fractional_amount_is_rejected(self) -> None:
        """Minor units are integers; 85000.5 cents is not a real amount."""
        with pytest.raises(ValidationError):
            salary_payload(amount_minor=85000.5)

    def test_effective_before_hire_date_is_rejected(
        self, service: SalaryRecordService, employee: Employee
    ) -> None:
        with pytest.raises(DomainValidationError, match="hire date"):
            service.create_for_employee(
                employee.id, salary_payload(effective_from=date(2019, 6, 1))
            )


class TestInvalidCurrencyValues:
    @pytest.mark.parametrize("currency_code", ["XXX", "ZZZ", "BTC"])
    def test_unsupported_currency_is_rejected_by_the_schema(self, currency_code: str) -> None:
        with pytest.raises(ValidationError, match="Unsupported currency"):
            salary_payload(currency_code=currency_code)

    @pytest.mark.parametrize("currency_code", ["US", "USDD", ""])
    def test_malformed_currency_length_is_rejected(self, currency_code: str) -> None:
        with pytest.raises(ValidationError):
            salary_payload(currency_code=currency_code)

    def test_unsupported_currency_is_rejected_by_the_service(
        self, service: SalaryRecordService, employee: Employee
    ) -> None:
        """The service re-validates, so no bad code can reach the database."""
        payload = salary_payload().model_copy(update={"currency_code": "XXX"})

        with pytest.raises(UnsupportedCurrencyError):
            service.create_for_employee(employee.id, payload)


class TestEffectivePeriodRules:
    def test_effective_to_before_effective_from_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="effective_to"):
            salary_payload(effective_from=date(2023, 1, 1), effective_to=date(2022, 1, 1))

    def test_zero_width_period_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            salary_payload(effective_from=date(2023, 1, 1), effective_to=date(2023, 1, 1))

    def test_a_raise_closes_the_previous_record(
        self, service: SalaryRecordService, employee: Employee
    ) -> None:
        """The ordinary raise path: the old record ends the day the new begins."""
        first = service.create_for_employee(employee.id, salary_payload())
        raise_date = date(2022, 4, 1)

        second = service.create_for_employee(
            employee.id,
            salary_payload(
                amount_minor=9_200_000,
                effective_from=raise_date,
                change_reason=SalaryChangeReason.MERIT,
            ),
        )

        assert first.effective_to == raise_date
        assert second.effective_to is None

    def test_overlapping_period_is_rejected(
        self, service: SalaryRecordService, employee: Employee
    ) -> None:
        service.create_for_employee(
            employee.id, salary_payload(effective_from=HIRE_DATE, effective_to=date(2023, 1, 1))
        )

        with pytest.raises(OverlappingSalaryPeriodError):
            service.create_for_employee(
                employee.id,
                salary_payload(effective_from=date(2022, 1, 1), effective_to=date(2022, 6, 1)),
            )

    def test_abutting_periods_are_allowed(
        self, service: SalaryRecordService, employee: Employee
    ) -> None:
        """[hire, 2023-01-01) then [2023-01-01, ...) share no day."""
        service.create_for_employee(
            employee.id, salary_payload(effective_from=HIRE_DATE, effective_to=date(2023, 1, 1))
        )

        second = service.create_for_employee(
            employee.id, salary_payload(effective_from=date(2023, 1, 1))
        )

        assert second.id is not None

    def test_rejected_create_leaves_existing_records_untouched(
        self, service: SalaryRecordService, employee: Employee
    ) -> None:
        """A rejected create must not half-apply."""
        first = service.create_for_employee(
            employee.id, salary_payload(effective_from=HIRE_DATE, effective_to=date(2021, 1, 1))
        )
        current = service.create_for_employee(
            employee.id, salary_payload(effective_from=date(2021, 1, 1))
        )

        with pytest.raises(OverlappingSalaryPeriodError):
            service.create_for_employee(
                employee.id,
                salary_payload(effective_from=date(2020, 6, 1), effective_to=date(2020, 9, 1)),
            )

        assert first.effective_to == date(2021, 1, 1)
        assert current.effective_to is None

    def test_different_pay_types_may_overlap(
        self, service: SalaryRecordService, employee: Employee
    ) -> None:
        """A bonus runs alongside base pay; only same-type overlap is a clash."""
        service.create_for_employee(employee.id, salary_payload(pay_type=PayType.BASE))

        bonus = service.create_for_employee(
            employee.id, salary_payload(pay_type=PayType.BONUS, amount_minor=500_000)
        )

        assert bonus.pay_type is PayType.BONUS
