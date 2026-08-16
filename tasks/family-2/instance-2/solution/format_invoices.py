"""Reference implementation of step 8 of `compute_invoices`.

Emit the list of
`(order_id, customer_name, line_total, discount, tax, final_amount)`
tuples sorted by `customer_name` ascending, with `order_id` as
the secondary sort key for ties.

`final_amount = line_total - discount + tax`. Each of
line_total, discount, tax and final_amount is rounded to two
decimal places and cast to float so whole-number amounts are
reported as float rather than int (the same trap closed off in
Family 1's Component A).
"""

from __future__ import annotations


def _round2(value):
    return float(round(value, 2))


def format_invoices(records):
    ordered = sorted(
        records, key=lambda r: (r["customer_name"], r["order_id"]))
    out = []
    for r in ordered:
        final_amount = r["line_total"] - r["discount"] + r["tax"]
        out.append((
            r["order_id"],
            r["customer_name"],
            _round2(r["line_total"]),
            _round2(r["discount"]),
            _round2(r["tax"]),
            _round2(final_amount),
        ))
    return out
