"""Reference implementation of step 3 of `compute_invoices`.

Look up each record's customer_id in the `customers` dictionary
and extend the record with the customer's name and tier.

Records whose customer_id is not in the lookup are dropped. This
is the spec choice in Instance 2 (the alternative would be to
keep them with a sentinel tier).
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
        })
    return out
