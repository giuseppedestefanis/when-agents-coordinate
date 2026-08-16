"""Reference implementation of step 15 of `process_billing`.

Sort records by final_amount descending, then order_id ascending, and
add a 1-based `rank` equal to the position in that order. The records
are returned in ranked order. Ranking uses the unrounded final_amount.
Agents do not see this file during a run.
"""
from __future__ import annotations


def rank_orders(records):
    ordered = sorted(records,
                     key=lambda r: (-r["final_amount"], r["order_id"]))
    return [{**r, "rank": i + 1} for i, r in enumerate(ordered)]
