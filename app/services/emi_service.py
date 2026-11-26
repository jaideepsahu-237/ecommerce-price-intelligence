"""EMI calculation and pricing service.

Implements the standard reducing-balance EMI formula:
    P = Financed amount (Price - Down Payment)
    r = Monthly interest rate (Annual rate / 12 / 100)
    n = Tenure in months

    EMI = P * r * (1 + r)^n / ((1 + r)^n - 1)
If r == 0 (no-cost EMI), EMI = P / n.
"""

from typing import Optional


class EmiService:

    @staticmethod
    def calculate_emi(
        price: float,
        down_payment: float = 0.0,
        tenure_months: int = 12,
        annual_rate: float = 14.0,
    ) -> dict:
        """Calculate indicative monthly EMI and total repayment cost."""
        if price <= 0:
            return {
                "financed_amount": 0.0,
                "monthly_emi": 0.0,
                "total_repayment": 0.0,
                "total_interest": 0.0,
                "tenure_months": tenure_months,
                "annual_rate": annual_rate,
            }

        financed_amount = max(0.0, price - down_payment)

        if financed_amount == 0.0 or tenure_months <= 0:
            return {
                "financed_amount": financed_amount,
                "monthly_emi": 0.0,
                "total_repayment": 0.0,
                "total_interest": 0.0,
                "tenure_months": tenure_months,
                "annual_rate": annual_rate,
            }

        # 0% / No-Cost EMI case
        if annual_rate <= 0:
            monthly_emi = round(financed_amount / tenure_months, 2)
            total_repayment = round(monthly_emi * tenure_months, 2)
            return {
                "financed_amount": round(financed_amount, 2),
                "monthly_emi": monthly_emi,
                "total_repayment": total_repayment,
                "total_interest": 0.0,
                "tenure_months": tenure_months,
                "annual_rate": annual_rate,
            }

        # Standard reducing-balance formula
        r = (annual_rate / 100.0) / 12.0
        n = tenure_months
        factor = (1.0 + r) ** n
        monthly_emi = financed_amount * r * factor / (factor - 1.0)
        total_repayment = monthly_emi * n
        total_interest = total_repayment - financed_amount

        return {
            "financed_amount": round(financed_amount, 2),
            "monthly_emi": round(monthly_emi, 2),
            "total_repayment": round(total_repayment, 2),
            "total_interest": round(total_interest, 2),
            "tenure_months": tenure_months,
            "annual_rate": annual_rate,
        }
