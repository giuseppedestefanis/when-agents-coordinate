"""Reference implementation for Family 1, Instance 2: build_report.

This is a correct implementation of the integrated specification in
memory/tasks/family-1/instance-2.md. Its purpose in the replication package is
to validate the verifier: the test suite in verifier.py must pass against this
file. During an experimental run the agent team produces its own solution.py
in an isolated working directory, and this reference file is never shown to
the agents.
"""


def build_report(records, settings):
    dropped = 0
    survivors = []
    start, end = settings["day_range"]
    for rec in records:
        if not _is_valid(rec):
            dropped += 1
            continue
        if rec["status"] not in settings["active_statuses"]:
            continue
        if not (start <= rec["day"] <= end):
            continue
        survivors.append(rec)
    totals = {}
    for rec in survivors:
        category = settings["category_map"].get(rec["category"],
                                                rec["category"])
        totals[category] = totals.get(category, 0) + rec["amount"]
    entries = [
        {"category": category, "total": round(float(total), 2)}
        for category, total in totals.items()
        if total >= settings["min_total"]
    ]
    _sort(entries, settings["sort_by"])
    return {
        "categories": entries,
        "record_count": len(survivors),
        "category_count": len(entries),
        "dropped": dropped,
    }


def _is_valid(rec):
    return (
        isinstance(rec.get("id"), str) and rec["id"] != ""
        and isinstance(rec.get("category"), str) and rec["category"] != ""
        and isinstance(rec.get("amount"), (int, float)) and rec["amount"] >= 0
        and isinstance(rec.get("day"), int) and rec["day"] >= 0
        and isinstance(rec.get("status"), str) and rec["status"] != ""
    )


def _sort(entries, sort_by):
    if sort_by == "category":
        entries.sort(key=lambda e: e["category"])
    elif sort_by == "total":
        entries.sort(key=lambda e: (-e["total"], e["category"]))
