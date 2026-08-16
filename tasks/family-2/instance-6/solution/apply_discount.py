"""Reference implementation of step 9 of `process_billing`.

Add discount_rate (bronze 0.00, silver 0.05, gold 0.10) and
discount = line_total * discount_rate; drop records whose
customer_tier is none of these. Agents do not see this file.
"""
from __future__ import annotations

TIER_RATES = {"bronze": 0.00, "silver": 0.05, "gold": 0.10}


def apply_discount(records):
    out = []
    for r in records:
        rate = TIER_RATES.get(r["customer_tier"])
        if rate is None:
            continue
        out.append({**r, "discount_rate": rate,
                    "discount": r["line_total"] * rate})
    return out
