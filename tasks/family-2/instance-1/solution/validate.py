"""Reference implementation of step 2 of `summarise_transactions`.

Drop records the parse step marked invalid; drop records whose
amount is negative or whose category is not in the allowed set;
drop the `invalid` flag from the surviving records.

The allowed set is fixed by the spec: groceries, transport, rent,
utilities, entertainment. The amount comparison is `>= 0`, so a
record with `amount == 0` is valid (canonical B1 in the conflict
instance).
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
