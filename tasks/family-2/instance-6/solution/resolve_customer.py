"""Reference implementation of step 4 of `process_billing`.

Attach customer_name, customer_tier and customer_region from the
customers lookup; drop records whose customer_id is unknown. Agents do
not see this file during a run.
"""
from __future__ import annotations


def resolve_customer(records, customers):
    out = []
    for record in records:
        info = customers.get(record["customer_id"])
        if info is None:
            continue
        out.append({
            **record,
            "customer_name": info["name"],
            "customer_tier": info["tier"],
            "customer_region": info["region"],
        })
    return out
