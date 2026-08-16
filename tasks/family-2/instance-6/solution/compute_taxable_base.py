"""Reference implementation of step 11 of `process_billing`.

Add taxable_base = line_total + surcharge - discount - loyalty_credit
(float, unrounded). Agents do not see this file during a run.
"""
from __future__ import annotations


def compute_taxable_base(records):
    return [
        {**r, "taxable_base": (r["line_total"] + r["surcharge"]
                               - r["discount"] - r["loyalty_credit"])}
        for r in records
    ]
