"""Reference implementation of step 5 of `compute_invoices`.

Add `line_total = quantity * price_per_unit` to each record.

No rounding here. Rounding is deferred to step 8 to avoid
compounding rounding errors through the chain.
"""

from __future__ import annotations


def compute_line_totals(records):
    return [
        {**r, "line_total": float(r["quantity"] * r["price_per_unit"])}
        for r in records
    ]
