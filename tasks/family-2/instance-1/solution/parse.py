"""Reference implementation of step 1 of `summarise_transactions`.

Coerce each raw transaction record's `date` to a `datetime.date`,
`amount` to a `float`, and `category` to a stripped lowercase
string. Mark records that fail any coercion as invalid by setting
their `invalid` flag to `True` and carrying them forward; the
validate step later drops them.

This file is the reference; it is used to validate the verifier
in `tasks/family-2/instance-1/verifier.py`. Agents do not see it
during a run.
"""

from __future__ import annotations

from datetime import date, datetime


def _parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_amount(value):
    # bool is a subclass of int in Python; the spec explicitly excludes
    # bool values from amount coercion.
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


def _parse_category(value):
    if not isinstance(value, str):
        return None
    return value.strip().lower()


def parse(records):
    out = []
    for raw in records:
        parsed = {
            "date": _parse_date(raw.get("date")),
            "amount": _parse_amount(raw.get("amount")),
            "category": _parse_category(raw.get("category")),
        }
        parsed["invalid"] = (
            parsed["date"] is None
            or parsed["amount"] is None
            or parsed["category"] is None
        )
        out.append(parsed)
    return out
