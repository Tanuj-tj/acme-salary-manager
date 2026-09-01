"""Business rules for salary amounts.

Pure functions, so they can be unit tested without a database and reused by
both the API schema layer and the service layer.
"""

from __future__ import annotations

from app.core.errors import InvalidSalaryAmountError
from app.domain.money import Money


def validate_salary_amount(amount: Money) -> None:
    """Raise unless the amount is a strictly positive sum of money.

    Zero is rejected along with negatives: an unpaid engagement is modelled by
    the absence of a salary record or by employment status, not by a zero-value
    record that would silently drag down every average.
    """
    if not amount.is_positive:
        raise InvalidSalaryAmountError(
            f"Salary amount must be greater than zero, got {amount}",
            context={
                "amount_minor": amount.amount_minor,
                "currency_code": amount.currency_code,
            },
        )
