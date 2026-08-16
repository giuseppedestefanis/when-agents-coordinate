"""Reference implementation of step 1 of `summarise_transactions_v2`.

Identical coercion logic to Instance 1's parse, with one
addition: step 1's specification additionally defines the
`CATEGORY_ORDER` constant. It is used by step 4 (format_output)
as the secondary sort key. CATEGORY_ORDER is exposed here at
module level so the reference `format_output.py` can import it
directly; the agent who holds step 4 must obtain its value
through coordination with the agent who holds step 1.

Agents do not see this file during a run.
"""

from __future__ import annotations

from datetime import datetime

CATEGORY_ORDER = (
    "groceries", "transport", "rent", "utilities", "entertainment",
)


def _parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_amount(value):
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
