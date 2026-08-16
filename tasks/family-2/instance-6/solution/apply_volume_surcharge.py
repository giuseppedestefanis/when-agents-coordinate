"""Reference implementation of step 8 of `process_billing`.

Add surcharge = 0.02 * line_total when quantity > 100, else 0.0
(float, unrounded). Agents do not see this file during a run.
"""
from __future__ import annotations

SURCHARGE_RATE = 0.02
SURCHARGE_QUANTITY_THRESHOLD = 100


def apply_volume_surcharge(records):
    out = []
    for r in records:
        surcharge = (SURCHARGE_RATE * r["line_total"]
                     if r["quantity"] > SURCHARGE_QUANTITY_THRESHOLD
                     else 0.0)
        out.append({**r, "surcharge": surcharge})
    return out
