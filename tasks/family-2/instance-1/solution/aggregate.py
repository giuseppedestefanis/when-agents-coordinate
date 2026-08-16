"""Reference implementation of step 3 of `summarise_transactions`.

Group validated records by year-month (`YYYY-MM`) and sum the
amounts. The output is a plain dictionary; the dictionary's keys
are not ordered, and the sums are unrounded. Rounding is deferred
to step 4 so that compounding rounding errors do not accumulate
through the chain.
"""

from __future__ import annotations


def aggregate(validated):
    totals = {}
    for record in validated:
        month = record["date"].strftime("%Y-%m")
        totals[month] = totals.get(month, 0.0) + record["amount"]
    return totals
