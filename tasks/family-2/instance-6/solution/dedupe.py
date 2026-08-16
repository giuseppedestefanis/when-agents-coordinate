"""Reference implementation of step 3 of `process_billing`.

Drop records whose order_id has already appeared earlier in the list
(keep the first occurrence; stable). Agents do not see this file.
"""
from __future__ import annotations


def dedupe(records):
    seen = set()
    out = []
    for record in records:
        if record["order_id"] in seen:
            continue
        seen.add(record["order_id"])
        out.append(record)
    return out
