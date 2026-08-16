"""Reference implementation of step 5 of `process_billing`.

Attach product_category and product_taxable from the products lookup;
drop records whose product_id is unknown. Agents do not see this file.
"""
from __future__ import annotations


def resolve_product(records, products):
    out = []
    for record in records:
        info = products.get(record["product_id"])
        if info is None:
            continue
        out.append({
            **record,
            "product_category": info["category"],
            "product_taxable": info["taxable"],
        })
    return out
