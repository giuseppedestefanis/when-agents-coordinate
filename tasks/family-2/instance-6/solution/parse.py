"""Reference implementation of step 1 of `process_billing`.

Coerce each raw order's five fields to typed values (str/str/str/
int>=0/float; bool excluded as a trap) and set `invalid` True if any
is None. Agents do not see this file during a run.
"""
from __future__ import annotations


def _parse_str(value):
    return value if isinstance(value, str) else None


def _parse_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if (value.is_integer() and value >= 0) else None
    if isinstance(value, str):
        try:
            n = int(value)
        except ValueError:
            return None
        return n if n >= 0 else None
    return None


def _parse_float(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def parse(orders):
    out = []
    for raw in orders:
        parsed = {
            "order_id": _parse_str(raw.get("order_id")),
            "customer_id": _parse_str(raw.get("customer_id")),
            "product_id": _parse_str(raw.get("product_id")),
            "quantity": _parse_int(raw.get("quantity")),
            "price_per_unit": _parse_float(raw.get("price_per_unit")),
        }
        parsed["invalid"] = any(
            parsed[k] is None
            for k in ("order_id", "customer_id", "product_id",
                      "quantity", "price_per_unit"))
        out.append(parsed)
    return out
