"""Reference implementation of step 4 of `summarise_transactions_v2`.

Two-key sort: primary key is month ascending (lexicographic on
YYYY-MM, which coincides with chronological order on valid
year-month strings); secondary key is category in the order
given by CATEGORY_ORDER, the constant defined in step 1's
specification.

This reference imports CATEGORY_ORDER from the reference
parse.py. The Instance 4 spec also permits the reference to hold
a local copy that matches; either is acceptable in the
reference because only the behaviour is checked. Importing keeps
the constant single-sourced and makes the cross-step dependency
explicit in the code.
"""

from __future__ import annotations

from parse import CATEGORY_ORDER

_CATEGORY_RANK = {name: i for i, name in enumerate(CATEGORY_ORDER)}


def format_output(totals):
    keys = sorted(
        totals,
        key=lambda k: (k[0], _CATEGORY_RANK[k[1]]),
    )
    return [
        (month, category, float(round(totals[(month, category)], 2)))
        for (month, category) in keys
    ]
