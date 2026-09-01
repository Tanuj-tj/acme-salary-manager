"""Employee ORM model.

Holds identity and employment facts only. An employee deliberately has no
salary column: compensation is effective-dated history, modelled by
``SalaryRecord``. See doc/architecture.md section 2.1.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.domain.enums import EmploymentStatus

if TYPE_CHECKING:
    from app.models.salary_record import SalaryRecord


class Employee(TimestampMixin, Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Stable identifier owned by the upstream HRIS. External references use
    # this, never the surrogate primary key.
    employee_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    work_email: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    job_title: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(120), index=True)

    # ISO 3166-1 alpha-2. Drives which salary band and currency apply.
    country_code: Mapped[str] = mapped_column(String(2), index=True)

    hire_date: Mapped[date] = mapped_column(Date)
    termination_date: Mapped[date | None] = mapped_column(Date, default=None)

    status: Mapped[EmploymentStatus] = mapped_column(
        Enum(
            EmploymentStatus,
            native_enum=False,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            validate_strings=True,
        ),
        default=EmploymentStatus.ACTIVE,
    )

    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), default=None, index=True
    )

    salary_records: Mapped[list[SalaryRecord]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SalaryRecord.effective_from.desc()",
    )

    manager: Mapped[Employee | None] = relationship(
        remote_side="Employee.id",
        back_populates="direct_reports",
    )
    direct_reports: Mapped[list[Employee]] = relationship(back_populates="manager")

    __table_args__ = (
        CheckConstraint(
            "termination_date IS NULL OR termination_date >= hire_date",
            name="termination_after_hire",
        ),
        CheckConstraint("manager_id IS NULL OR manager_id <> id", name="manager_is_not_self"),
        Index("ix_employees_status_department", "status", "department"),
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def __repr__(self) -> str:
        return f"<Employee id={self.id} number={self.employee_number!r}>"
