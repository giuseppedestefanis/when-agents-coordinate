"""Reference implementation of step 6 of `process_billing`.

Drop records whose customer_region is embargoed. EMBARGOED_REGIONS is
defined here. Agents do not see this file during a run.
"""
from __future__ import annotations

EMBARGOED_REGIONS = ("crimson", "umber")


def filter_embargo(records):
    return [r for r in records
            if r["customer_region"] not in EMBARGOED_REGIONS]
