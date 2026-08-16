"""Reference implementation of step 2 of `process_billing`.

Keep records that are not invalid, with quantity > 0 and
price_per_unit >= 0; drop the `invalid` key. Agents do not see this
file during a run.
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
        out.append({k: v for k, v in record.items() if k != "invalid"})
    return out
