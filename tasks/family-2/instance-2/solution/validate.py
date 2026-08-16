"""Reference implementation of step 2 of `compute_invoices`.

Drop records the parse step marked invalid; drop records whose
quantity is not strictly greater than zero or whose
price_per_unit is negative. Drop the `invalid` flag from the
surviving records.

The spec says quantity > 0 (zero rejected) and price >= 0 (zero
accepted). These are the canonical boundaries for Instance 2;
there is no conflict variant on this instance.
"""

from __future__ import annotations


def validate(parsed):
    out = []
    for record in parsed:
        if record["invalid"]:
            continue
        if record["quantity"] <= 0:
            continue
        if record["price_per_unit"] < 0:
            continue
        survivor = {k: v for k, v in record.items() if k != "invalid"}
        out.append(survivor)
    return out
