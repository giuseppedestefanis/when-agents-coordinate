"""Reference implementation of step 7 of `compute_invoices`.

Add the unrounded `tax` to each record:

    after_discount = line_total - discount
    tax_rate       = 0.20 if product_taxable else 0.00
    tax            = after_discount * tax_rate
"""

from __future__ import annotations

TAXABLE_RATE = 0.20


def compute_tax(records):
    out = []
    for record in records:
        after_discount = record["line_total"] - record["discount"]
        rate = TAXABLE_RATE if record["product_taxable"] else 0.00
        out.append({**record, "tax": after_discount * rate})
    return out
