"""Reference implementation of step 4 of `summarise_transactions`.

Round each month's total to two decimal places, cast to float
(so whole-number totals are reported as float rather than int,
the same trap closed off in Family 1's Component A), and emit
the list of `(month, total)` pairs sorted by month ascending.

Sorting is by lexicographic order on the `YYYY-MM` string. For
valid year-month strings the lexicographic order coincides with
chronological order, including across year boundaries
(`"2025-12" < "2026-01"`), because the format is fixed-width.
"""

from __future__ import annotations


def format_output(totals):
    return [
        (month, float(round(totals[month], 2)))
        for month in sorted(totals)
    ]
