"""Reference implementation for Family 1, Instance 1: process_orders.

This is a correct implementation of the integrated specification in
memory/tasks/family-1/instance-1.md. Its purpose in the replication package is
to validate the verifier: the test suite in verifier.py must pass against this
file. During an experimental run the agent team produces its own solution.py
in an isolated working directory, and this reference file is never shown to
the agents.
"""


def process_orders(orders, config):
    processed = []
    rejected = 0
    for order in orders:
        if not _is_valid(order):
            rejected += 1
            continue
        processed.append({
            "id": order["id"],
            "customer": order["customer"],
            "final_amount": _discounted(order, config),
        })
    _sort(processed, config["sort_by"])
    total = round(float(sum(e["final_amount"] for e in processed)), 2)
    return {
        "processed": processed,
        "count": len(processed),
        "total": total,
        "rejected": rejected,
    }


def _is_valid(order):
    return (
        isinstance(order.get("id"), str) and order["id"] != ""
        and isinstance(order.get("customer"), str) and order["customer"] != ""
        and isinstance(order.get("amount"), (int, float))
        and order["amount"] >= 0
        and isinstance(order.get("quantity"), int)
        and order["quantity"] > 0
    )


def _discounted(order, config):
    amount = float(order["amount"])
    if order["quantity"] >= config["bulk_threshold"]:
        amount *= (1 - config["bulk_discount"])
    if order["customer"] in config["loyalty_customers"]:
        amount *= (1 - config["loyalty_discount"])
    return round(amount, 2)


def _sort(processed, sort_by):
    if sort_by == "amount":
        processed.sort(key=lambda e: (e["final_amount"], e["id"]))
    elif sort_by == "id":
        processed.sort(key=lambda e: e["id"])
