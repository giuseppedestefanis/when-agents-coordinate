"""Reference implementation of step 7 of `process_billing`.

Add line_total = quantity * price_per_unit (float, unrounded). Agents
do not see this file during a run.
"""
from __future__ import annotations


def compute_line_totals(records):
    return [
        {**r, "line_total": float(r["quantity"] * r["price_per_unit"])}
        for r in records
    ]
