"""Reference implementation of step 6 of `compute_invoices`.

Add a tier-specific `discount_rate` and the unrounded `discount`
(line_total * discount_rate) to each record.

Tier-rate table:
  - bronze: 0.00
  - silver: 0.05
  - gold:   0.10

Records whose customer_tier is none of these are dropped (a
defensive case, not expected in well-formed input).
"""

from __future__ import annotations

TIER_RATES = {
    "bronze": 0.00,
    "silver": 0.05,
    "gold": 0.10,
}


def apply_discount(records):
    out = []
    for record in records:
        rate = TIER_RATES.get(record["customer_tier"])
        if rate is None:
            continue
        out.append({
            **record,
            "discount_rate": rate,
            "discount": record["line_total"] * rate,
        })
    return out
