"""Reference implementation of step 10 of `process_billing`.

Add loyalty_credit = 0.01 * line_total when customer_tier is "gold"
and line_total >= 1000, else 0.0 (float, unrounded). Agents do not
see this file during a run.
"""
from __future__ import annotations

LOYALTY_RATE = 0.01
LOYALTY_VALUE_THRESHOLD = 1000


def apply_loyalty_credit(records):
    out = []
    for r in records:
        credit = (LOYALTY_RATE * r["line_total"]
                  if (r["customer_tier"] == "gold"
                      and r["line_total"] >= LOYALTY_VALUE_THRESHOLD)
                  else 0.0)
        out.append({**r, "loyalty_credit": credit})
    return out
