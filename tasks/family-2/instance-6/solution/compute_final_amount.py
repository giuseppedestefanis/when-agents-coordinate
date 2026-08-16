"""Reference implementation of step 14 of `process_billing`.

Add final_amount = taxable_base + tax + shipping (float, unrounded).
Agents do not see this file during a run.
"""
from __future__ import annotations


def compute_final_amount(records):
    return [
        {**r, "final_amount": r["taxable_base"] + r["tax"] + r["shipping"]}
        for r in records
    ]
