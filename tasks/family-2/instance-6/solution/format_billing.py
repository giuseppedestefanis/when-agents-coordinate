"""Reference implementation of step 16 of `process_billing`.

Emit (order_id, customer_name, final_amount, rank) tuples in ranked
order (already sorted by step 15). final_amount is rounded to two
decimal places and cast to float so whole-number amounts are reported
as float. Agents do not see this file during a run.
"""
from __future__ import annotations


def _round2(value):
    return float(round(value, 2))


def format_billing(records):
    return [
        (r["order_id"], r["customer_name"], _round2(r["final_amount"]),
         r["rank"])
        for r in records
    ]
