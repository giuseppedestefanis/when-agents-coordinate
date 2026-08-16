"""Reference implementation of step 3 of `summarise_transactions_v2`.

Group validated records by the pair (month, category), where
month is the year-month string of the record's date and category
is the record's category string. Sum each group's amounts
unrounded.

Modified from Instance 1: the keys are now tuples
`(month, category)` rather than month strings. The finer grain
is the v2 task's grouping change.
"""

from __future__ import annotations


def aggregate(validated):
    totals = {}
    for record in validated:
        key = (record["date"].strftime("%Y-%m"), record["category"])
        totals[key] = totals.get(key, 0.0) + record["amount"]
    return totals
