"""EMI calculation and pricing service.

Implements the standard reducing-balance EMI formula:
    P = Financed amount (Price - Down Payment)
    r = Monthly interest rate (Annual rate / 12 / 100)
    n = Tenure in months

    EMI = P * r * (1 + r)^n / ((1 + r)^n - 1)
If r == 0 (no-cost EMI), EMI = P / n.
"""

import re
from typing import Optional


_BANK_RE = re.compile(
    r"\b(HDFC|ICICI|SBI|Axis|Kotak|IDFC|Yes\s*Bank|HSBC|OneCard|Amex|BOB|Bank\s*of\s*Baroda)\b",
    re.IGNORECASE,
)
_FLAT_DISCOUNT_RE = re.compile(
    r"(?:₹|Rs\.?\s*)([\d,]+(?:\.\d+)?)\s*(?:off|discount|cashback|instant)?",
    re.IGNORECASE,
)
_PCT_DISCOUNT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*(?:off|discount|cashback)", re.IGNORECASE)


def parse_offer_details(
    offer_text: Optional[str], selling_price: float
) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """Extract (offer_discount, offer_type, bank) from publicly visible offer text."""
    if not offer_text or selling_price <= 0:
        return None, None, None

    bank_m = _BANK_RE.search(offer_text)
    bank = bank_m.group(1).strip() if bank_m else None

    lower = offer_text.lower()
    if bank or "card" in lower or "bank" in lower or "cashback" in lower:
        offer_type = "bank"
    elif "no cost emi" in lower or "no-cost emi" in lower or "emi" in lower:
        offer_type = "emi"
    elif "exchange" in lower:
        offer_type = "exchange"
    else:
        offer_type = "discount"

    offer_discount = None
    # Check "Best Price ₹X" style text first
    best_m = re.search(r"best\s*price\s*[:\-]?\s*(?:₹|Rs\.?\s*)([\d,]+(?:\.\d+)?)", offer_text, re.IGNORECASE)
    if best_m:
        best_val = float(best_m.group(1).replace(",", ""))
        if 0 < best_val < selling_price:
            offer_discount = round(selling_price - best_val, 2)
    else:
        flat_m = _FLAT_DISCOUNT_RE.search(offer_text)
        if flat_m:
            val = float(flat_m.group(1).replace(",", ""))
            if 0 < val < selling_price:
                offer_discount = round(val, 2)
        else:
            pct_m = _PCT_DISCOUNT_RE.search(offer_text)
            if pct_m:
                pct = float(pct_m.group(1))
                if 0 < pct < 50:
                    offer_discount = round(selling_price * (pct / 100.0), 2)

    return offer_discount, offer_type, bank


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
