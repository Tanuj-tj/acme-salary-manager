"""ORM models.

Imported as a package so that ``Base.metadata`` is fully populated before
Alembic autogenerate or ``create_all`` runs.
"""

from app.db.base import Base
from app.models.employee import Employee
from app.models.salary_record import SalaryRecord

__all__ = ["Base", "Employee", "SalaryRecord"]
