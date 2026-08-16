"""Reference implementation of step 13 of `process_billing`.

Add shipping per product_category from SHIPPING_FEES (defined here);
a category absent from the map gets the default 5.0. Agents do not
see this file during a run.
"""
from __future__ import annotations

SHIPPING_FEES = {"standard": 5.0, "bulky": 15.0, "digital": 0.0}
DEFAULT_SHIPPING = 5.0


def apply_shipping(records):
    return [
        {**r, "shipping": SHIPPING_FEES.get(r["product_category"],
                                            DEFAULT_SHIPPING)}
        for r in records
    ]
