"""Reference implementation of step 4 of `compute_invoices`.

Look up each record's product_id in the `products` dictionary
and extend the record with the product's category and taxable
flag.

Records whose product_id is not in the lookup are dropped, the
same convention as resolve_customer.
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
