"""Verifier test suite for Family 1, Instance 1: process_orders.

Run with: pytest tasks/family-1/instance-1/verifier.py
Expects solution.py in the same directory, exposing process_orders.

This file is extracted verbatim from section 5 of
memory/tasks/family-1/instance-1.md, which is the design source of truth. It
is not shown to the agents during a run.
"""

from solution import process_orders

BASE_CONFIG = {
    "bulk_threshold": 10,
    "bulk_discount": 0.10,
    "loyalty_customers": ["acme", "globex"],
    "loyalty_discount": 0.20,
    "sort_by": "id",
}


def config(**overrides):
    """Return a copy of BASE_CONFIG with the given keys overridden."""
    cfg = dict(BASE_CONFIG)
    cfg.update(overrides)
    return cfg


def order(id="x", customer="nobody", amount=100, quantity=1):
    return {"id": id, "customer": customer, "amount": amount,
            "quantity": quantity}


# --- Component A: signature and return shape ---------------------------------

def test_return_has_exactly_four_keys():
    result = process_orders([order()], config())
    assert set(result) == {"processed", "count", "total", "rejected"}


def test_return_field_types():
    result = process_orders([order()], config())
    assert isinstance(result["processed"], list)
    assert isinstance(result["count"], int)
    assert isinstance(result["total"], float)
    assert isinstance(result["rejected"], int)


def test_processed_entry_shape():
    result = process_orders([order(id="a", customer="acme")], config())
    entry = result["processed"][0]
    assert set(entry) == {"id", "customer", "final_amount"}
    assert entry["id"] == "a"
    assert entry["customer"] == "acme"
    assert isinstance(entry["final_amount"], float)


# --- Component B: validation -------------------------------------------------

def test_rejects_empty_id():
    result = process_orders([order(id="")], config())
    assert result["count"] == 0
    assert result["rejected"] == 1
    assert result["processed"] == []


def test_rejects_non_string_id():
    result = process_orders([order(id=123)], config())
    assert result["rejected"] == 1


def test_rejects_empty_customer():
    result = process_orders([order(customer="")], config())
    assert result["rejected"] == 1


def test_rejects_negative_amount():
    result = process_orders([order(amount=-1)], config())
    assert result["rejected"] == 1


def test_rejects_zero_quantity():
    result = process_orders([order(quantity=0)], config())
    assert result["rejected"] == 1


def test_accepts_zero_amount():
    result = process_orders([order(amount=0)], config())
    assert result["count"] == 1
    assert result["processed"][0]["final_amount"] == 0.0


def test_accepts_float_amount():
    result = process_orders([order(amount=33.33)], config())
    assert result["count"] == 1
    assert result["processed"][0]["final_amount"] == 33.33


# --- Component C: discount ---------------------------------------------------

def test_no_discount():
    result = process_orders(
        [order(customer="nobody", amount=100, quantity=5)], config())
    assert result["processed"][0]["final_amount"] == 100.0


def test_bulk_discount_only():
    result = process_orders(
        [order(customer="nobody", amount=100, quantity=10)], config())
    assert result["processed"][0]["final_amount"] == 90.0


def test_loyalty_discount_only():
    result = process_orders(
        [order(customer="acme", amount=100, quantity=5)], config())
    assert result["processed"][0]["final_amount"] == 80.0


def test_both_discounts_compound():
    result = process_orders(
        [order(customer="globex", amount=100, quantity=12)], config())
    assert result["processed"][0]["final_amount"] == 72.0


def test_discount_rounds_to_two_places():
    result = process_orders(
        [order(customer="nobody", amount=99.99, quantity=10)], config())
    assert result["processed"][0]["final_amount"] == 89.99


# --- Component D: sorting ----------------------------------------------------

def test_sort_by_id():
    orders = [order(id="c"), order(id="a"), order(id="b")]
    result = process_orders(orders, config(sort_by="id"))
    assert [e["id"] for e in result["processed"]] == ["a", "b", "c"]


def test_sort_by_amount():
    orders = [
        order(id="a", amount=100, quantity=1),
        order(id="b", amount=50, quantity=1),
        order(id="c", amount=75, quantity=1),
    ]
    result = process_orders(orders, config(sort_by="amount"))
    assert [e["id"] for e in result["processed"]] == ["b", "c", "a"]


def test_sort_by_amount_ties_broken_by_id():
    orders = [
        order(id="z", amount=50, quantity=1),
        order(id="a", amount=50, quantity=1),
    ]
    result = process_orders(orders, config(sort_by="amount"))
    assert [e["id"] for e in result["processed"]] == ["a", "z"]


# --- Edge cases and combination ----------------------------------------------

def test_empty_input():
    result = process_orders([], config())
    assert result == {"processed": [], "count": 0, "total": 0.0,
                      "rejected": 0}


def test_all_invalid_input():
    orders = [order(id=""), order(customer=""), order(quantity=0)]
    result = process_orders(orders, config())
    assert result["count"] == 0
    assert result["rejected"] == 3
    assert result["processed"] == []
    assert result["total"] == 0.0


def test_mixed_validity_with_discounts_and_sorting():
    orders = [
        order(id="a", customer="acme", amount=100, quantity=5),
        order(id="", customer="x", amount=50, quantity=5),
        order(id="b", customer="nobody", amount=200, quantity=10),
        order(id="c", customer="y", amount=-5, quantity=5),
    ]
    result = process_orders(orders, config(sort_by="id"))
    assert result["count"] == 2
    assert result["rejected"] == 2
    assert [e["id"] for e in result["processed"]] == ["a", "b"]
    assert result["processed"][0]["final_amount"] == 80.0
    assert result["processed"][1]["final_amount"] == 180.0


def test_total_sums_final_amounts():
    orders = [
        order(id="a", customer="acme", amount=100, quantity=5),
        order(id="b", customer="nobody", amount=200, quantity=10),
    ]
    result = process_orders(orders, config())
    assert result["total"] == 260.0
