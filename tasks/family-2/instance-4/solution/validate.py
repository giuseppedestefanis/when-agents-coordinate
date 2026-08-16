"""Reference implementation of step 2 of `summarise_transactions_v2`.

Identical to Instance 1's validate. The v2 task changes the
aggregate and format steps; the validate step is unchanged.
"""

from __future__ import annotations

ALLOWED_CATEGORIES = {
    "groceries", "transport", "rent", "utilities", "entertainment",
}


def validate(parsed):
    out = []
    for record in parsed:
        if record["invalid"]:
            continue
        if record["amount"] < 0:
            continue
        if record["category"] not in ALLOWED_CATEGORIES:
            continue
        out.append({
            "date": record["date"],
            "amount": record["amount"],
            "category": record["category"],
        })
    return out
