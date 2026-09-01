"""initial employees and salary_records

Creates the two foundation tables. Note `uq_salary_records_open_period`: a
partial unique index enforcing "at most one open-ended record per employee and
pay type" in the database rather than only in service code. Emitted for both
SQLite and PostgreSQL via the dialect-specific `*_where` arguments.

Revision ID: 56cfe6471a39
Revises:
Create Date: 2026-09-01

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "56cfe6471a39"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_number", sa.String(length=32), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("work_email", sa.String(length=255), nullable=False),
        sa.Column("job_title", sa.String(length=120), nullable=False),
        sa.Column("department", sa.String(length=120), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("hire_date", sa.Date(), nullable=False),
        sa.Column("termination_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "on_leave",
                "terminated",
                name="employmentstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("manager_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "manager_id IS NULL OR manager_id <> id", name=op.f("ck_employees_manager_is_not_self")
        ),
        sa.CheckConstraint(
            "termination_date IS NULL OR termination_date >= hire_date",
            name=op.f("ck_employees_termination_after_hire"),
        ),
        sa.ForeignKeyConstraint(
            ["manager_id"],
            ["employees.id"],
            name=op.f("fk_employees_manager_id_employees"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_employees")),
    )
    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_employees_country_code"), ["country_code"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_employees_department"), ["department"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_employees_employee_number"), ["employee_number"], unique=True
        )
        batch_op.create_index(batch_op.f("ix_employees_manager_id"), ["manager_id"], unique=False)
        batch_op.create_index(
            "ix_employees_status_department", ["status", "department"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_employees_work_email"), ["work_email"], unique=True)

    op.create_table(
        "salary_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column(
            "pay_type",
            sa.Enum("base", "bonus", "allowance", name="paytype", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column(
            "pay_period",
            sa.Enum("annual", "monthly", "hourly", name="payperiod", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column(
            "change_reason",
            sa.Enum(
                "hire",
                "merit",
                "promotion",
                "market_adjustment",
                "demotion",
                "correction",
                "other",
                name="salarychangereason",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name=op.f("ck_salary_records_amount_is_positive")),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name=op.f("ck_salary_records_effective_period_is_valid"),
        ),
        sa.CheckConstraint(
            "length(currency_code) = 3", name=op.f("ck_salary_records_currency_code_is_iso4217")
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name=op.f("fk_salary_records_employee_id_employees"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_salary_records")),
    )
    with op.batch_alter_table("salary_records", schema=None) as batch_op:
        batch_op.create_index(
            "ix_salary_records_effective_range", ["effective_from", "effective_to"], unique=False
        )
        batch_op.create_index(
            "ix_salary_records_employee_effective", ["employee_id", "effective_from"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_salary_records_employee_id"), ["employee_id"], unique=False
        )
        batch_op.create_index(
            "uq_salary_records_open_period",
            ["employee_id", "pay_type"],
            unique=True,
            sqlite_where=sa.text("effective_to IS NULL"),
            postgresql_where=sa.text("effective_to IS NULL"),
        )


def downgrade() -> None:
    with op.batch_alter_table("salary_records", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_salary_records_open_period",
            sqlite_where=sa.text("effective_to IS NULL"),
            postgresql_where=sa.text("effective_to IS NULL"),
        )
        batch_op.drop_index(batch_op.f("ix_salary_records_employee_id"))
        batch_op.drop_index("ix_salary_records_employee_effective")
        batch_op.drop_index("ix_salary_records_effective_range")

    op.drop_table("salary_records")
    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_employees_work_email"))
        batch_op.drop_index("ix_employees_status_department")
        batch_op.drop_index(batch_op.f("ix_employees_manager_id"))
        batch_op.drop_index(batch_op.f("ix_employees_employee_number"))
        batch_op.drop_index(batch_op.f("ix_employees_department"))
        batch_op.drop_index(batch_op.f("ix_employees_country_code"))

    op.drop_table("employees")
