"""Reference implementation of step 12 of `process_billing`.

Add tax = taxable_base * 0.20 for taxable products, else 0.00
(float, unrounded). Agents do not see this file during a run.
"""
from __future__ import annotations

TAXABLE_RATE = 0.20


def compute_tax(records):
    out = []
    for r in records:
        rate = TAXABLE_RATE if r["product_taxable"] else 0.00
        out.append({**r, "tax": r["taxable_base"] * rate})
    return out
