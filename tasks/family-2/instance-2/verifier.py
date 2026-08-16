"""Verifier test suite for Family 2, Instance 2: compute_invoices.

Run during a run with: pytest tasks/family-2/instance-2/verifier.py
The runner adds the run's workspace to PYTHONPATH so the imports
below resolve to the agents' deliverables (parse.py, validate.py,
resolve_customer.py, resolve_product.py, compute_line_totals.py,
apply_discount.py, compute_tax.py, format_invoices.py, pipeline.py).

To validate this verifier against the reference solution locally:

    PYTHONPATH=tasks/family-2/instance-2/solution \\
        .venv/bin/pytest tasks/family-2/instance-2/verifier.py

Test count: 32 (8 unit + 3 integration listed in instance-2.md
Section 5, 3 unit + 5 integration from verifier-checklist.md, plus
13 additional tests at the verifier author's judgement to reach
the rough target of 32). The verifier-checklist's test-count table
records 13 open tests after the committed surface; that count is
satisfied by the additions below.
"""


from parse import parse
from validate import validate
from resolve_customer import resolve_customer
from resolve_product import resolve_product
from compute_line_totals import compute_line_totals
from apply_discount import apply_discount
from compute_tax import compute_tax
from format_invoices import format_invoices
from pipeline import compute_invoices


# --- Step 1 (parse) unit tests ---------------------------------------------

def test_parse_valid_order():
    out = parse([
        {"order_id": "O1", "customer_id": "C1", "product_id": "P1",
         "quantity": "3", "price_per_unit": "10.0"},
    ])
    assert out == [{"order_id": "O1", "customer_id": "C1",
                    "product_id": "P1", "quantity": 3,
                    "price_per_unit": 10.0, "invalid": False}]


def test_parse_bool_quantity_excluded():
    out = parse([
        {"order_id": "O1", "customer_id": "C1", "product_id": "P1",
         "quantity": True, "price_per_unit": "10.0"},
    ])
    assert out[0]["quantity"] is None
    assert out[0]["invalid"] is True


def test_parse_bool_price_excluded():
    out = parse([
        {"order_id": "O1", "customer_id": "C1", "product_id": "P1",
         "quantity": "3", "price_per_unit": True},
    ])
    assert out[0]["price_per_unit"] is None
    assert out[0]["invalid"] is True


def test_parse_missing_field_marks_invalid():
    out = parse([
        {"order_id": "O1", "customer_id": "C1", "product_id": "P1",
         "quantity": "3"},  # price_per_unit missing
    ])
    assert out[0]["price_per_unit"] is None
    assert out[0]["invalid"] is True


# --- Step 2 (validate) unit tests ------------------------------------------

def test_validate_drops_zero_quantity():
    parsed = [{"order_id": "O1", "customer_id": "C1",
               "product_id": "P1", "quantity": 0,
               "price_per_unit": 10.0, "invalid": False}]
    assert validate(parsed) == []


def test_validate_drops_invalid_flag():
    parsed = [{"order_id": "O1", "customer_id": "C1",
               "product_id": "P1", "quantity": 1,
               "price_per_unit": 10.0, "invalid": True}]
    assert validate(parsed) == []


def test_validate_drops_negative_price():
    parsed = [{"order_id": "O1", "customer_id": "C1",
               "product_id": "P1", "quantity": 1,
               "price_per_unit": -1.0, "invalid": False}]
    assert validate(parsed) == []


def test_validate_zero_price_kept():
    # Boundary: price >= 0 is valid; zero kept (parallels Instance 1's
    # validate_zero_amount_kept). Quantity > 0 is still required.
    parsed = [{"order_id": "O1", "customer_id": "C1",
               "product_id": "P1", "quantity": 1,
               "price_per_unit": 0.0, "invalid": False}]
    assert len(validate(parsed)) == 1


# --- Step 3 (resolve_customer) unit tests ----------------------------------

def test_resolve_customer_unknown_dropped():
    recs = [{"order_id": "O1", "customer_id": "C99",
             "product_id": "P1", "quantity": 1,
             "price_per_unit": 5.0}]
    customers = {"C1": {"name": "Alice", "tier": "gold"}}
    assert resolve_customer(recs, customers) == []


def test_resolve_customer_adds_name_and_tier():
    recs = [{"order_id": "O1", "customer_id": "C1",
             "product_id": "P1", "quantity": 1,
             "price_per_unit": 5.0}]
    customers = {"C1": {"name": "Alice", "tier": "gold"}}
    out = resolve_customer(recs, customers)
    assert len(out) == 1
    assert out[0]["customer_name"] == "Alice"
    assert out[0]["customer_tier"] == "gold"


# --- Step 4 (resolve_product) unit tests -----------------------------------

def test_resolve_product_unknown_dropped():
    recs = [{"order_id": "O1", "customer_id": "C1",
             "product_id": "P99", "quantity": 1,
             "price_per_unit": 5.0,
             "customer_name": "Alice", "customer_tier": "gold"}]
    products = {"P1": {"category": "x", "taxable": True}}
    assert resolve_product(recs, products) == []


def test_resolve_product_adds_category_and_taxable():
    recs = [{"order_id": "O1", "customer_id": "C1",
             "product_id": "P1", "quantity": 1,
             "price_per_unit": 5.0,
             "customer_name": "Alice", "customer_tier": "gold"}]
    products = {"P1": {"category": "books", "taxable": False}}
    out = resolve_product(recs, products)
    assert len(out) == 1
    assert out[0]["product_category"] == "books"
    assert out[0]["product_taxable"] is False


# --- Step 5 (compute_line_totals) unit tests -------------------------------

def test_compute_line_totals():
    recs = [{"order_id": "O1", "customer_id": "C1",
             "product_id": "P1", "quantity": 3,
             "price_per_unit": 10.0,
             "customer_name": "Alice", "customer_tier": "gold",
             "product_category": "x", "product_taxable": True}]
    out = compute_line_totals(recs)
    assert out[0]["line_total"] == 30.0


# --- Step 6 (apply_discount) unit tests ------------------------------------

def test_apply_discount_bronze_zero_rate():
    recs = [{"order_id": "O1", "customer_id": "C1",
             "product_id": "P1", "quantity": 1,
             "price_per_unit": 10.0,
             "customer_name": "Alice", "customer_tier": "bronze",
             "product_category": "x", "product_taxable": True,
             "line_total": 10.0}]
    out = apply_discount(recs)
    assert out[0]["discount_rate"] == 0.00
    assert out[0]["discount"] == 0.0


def test_apply_discount_silver():
    recs = [{"order_id": "O1", "customer_id": "C1",
             "product_id": "P1", "quantity": 3,
             "price_per_unit": 10.0,
             "customer_name": "Alice", "customer_tier": "silver",
             "product_category": "x", "product_taxable": True,
             "line_total": 30.0}]
    out = apply_discount(recs)
    assert out[0]["discount_rate"] == 0.05
    assert out[0]["discount"] == 1.5


def test_apply_discount_gold_rate():
    recs = [{"order_id": "O1", "customer_id": "C1",
             "product_id": "P1", "quantity": 1,
             "price_per_unit": 100.0,
             "customer_name": "Alice", "customer_tier": "gold",
             "product_category": "x", "product_taxable": True,
             "line_total": 100.0}]
    out = apply_discount(recs)
    assert out[0]["discount_rate"] == 0.10
    assert out[0]["discount"] == 10.0


# --- Step 7 (compute_tax) unit tests ---------------------------------------

def test_compute_tax_taxable():
    recs = [{"line_total": 30.0, "discount": 1.5,
             "product_taxable": True}]
    out = compute_tax(recs)
    assert out[0]["tax"] == (30.0 - 1.5) * 0.20


def test_compute_tax_non_taxable_branch():
    recs = [{"line_total": 30.0, "discount": 1.5,
             "product_taxable": False}]
    out = compute_tax(recs)
    assert out[0]["tax"] == 0.0


# --- Step 8 (format_invoices) unit tests -----------------------------------

def test_format_invoices_sort_by_customer_name():
    recs = [
        {"order_id": "O1", "customer_name": "Bob",
         "line_total": 10.0, "discount": 0.0, "tax": 2.0},
        {"order_id": "O2", "customer_name": "Alice",
         "line_total": 5.0, "discount": 0.0, "tax": 1.0},
    ]
    out = format_invoices(recs)
    assert [r[1] for r in out] == ["Alice", "Bob"]


def test_format_invoices_amounts_are_float():
    recs = [
        {"order_id": "O1", "customer_name": "Alice",
         "line_total": 10, "discount": 0, "tax": 2},
    ]
    out = format_invoices(recs)
    # line_total, discount, tax, final_amount are positions 2, 3, 4, 5.
    assert all(isinstance(out[0][i], float) for i in (2, 3, 4, 5))


def test_format_invoices_rounds_to_two_decimals():
    recs = [
        {"order_id": "O1", "customer_name": "Alice",
         "line_total": 12.349, "discount": 1.234, "tax": 0.567},
    ]
    out = format_invoices(recs)
    # Rounded values: line_total 12.35, discount 1.23, tax 0.57,
    # final_amount = round(12.349 - 1.234 + 0.567, 2) = round(11.682, 2) = 11.68
    assert out[0][2] == 12.35
    assert out[0][3] == 1.23
    assert out[0][4] == 0.57
    assert out[0][5] == 11.68


# --- Integration tests -----------------------------------------------------

def test_end_to_end_silver_taxable():
    orders = [{"order_id": "O1", "customer_id": "C1",
               "product_id": "P1", "quantity": "3",
               "price_per_unit": "10.0"}]
    reference = {
        "customers": {"C1": {"name": "Alice", "tier": "silver"}},
        "products": {"P1": {"category": "x", "taxable": True}},
    }
    out = compute_invoices(orders, reference)
    # line_total = 30.0, discount = 30 * 0.05 = 1.5,
    # after_discount = 28.5, tax = 28.5 * 0.20 = 5.7,
    # final = 28.5 + 5.7 = 34.2.
    assert out == [("O1", "Alice", 30.0, 1.5, 5.7, 34.2)]


def test_end_to_end_bronze_non_taxable_whole_numbers():
    orders = [{"order_id": "O1", "customer_id": "C1",
               "product_id": "P1", "quantity": "2",
               "price_per_unit": "5"}]
    reference = {
        "customers": {"C1": {"name": "Alice", "tier": "bronze"}},
        "products": {"P1": {"category": "x", "taxable": False}},
    }
    out = compute_invoices(orders, reference)
    # line_total = 10.0, discount = 0.0, tax = 0.0, final = 10.0
    assert out == [("O1", "Alice", 10.0, 0.0, 0.0, 10.0)]
    assert all(isinstance(v, float) for v in out[0][2:])


def test_end_to_end_sorts_by_customer_name():
    orders = [
        {"order_id": "O1", "customer_id": "C1", "product_id": "P1",
         "quantity": "1", "price_per_unit": "10"},
        {"order_id": "O2", "customer_id": "C2", "product_id": "P1",
         "quantity": "1", "price_per_unit": "10"},
    ]
    reference = {
        "customers": {
            "C1": {"name": "Bob",   "tier": "bronze"},
            "C2": {"name": "Alice", "tier": "bronze"},
        },
        "products": {"P1": {"category": "x", "taxable": False}},
    }
    out = compute_invoices(orders, reference)
    assert [r[1] for r in out] == ["Alice", "Bob"]


def test_end_to_end_all_three_tiers():
    orders = [
        {"order_id": "O1", "customer_id": "C1", "product_id": "P1",
         "quantity": "1", "price_per_unit": "100"},
        {"order_id": "O2", "customer_id": "C2", "product_id": "P1",
         "quantity": "1", "price_per_unit": "100"},
        {"order_id": "O3", "customer_id": "C3", "product_id": "P1",
         "quantity": "1", "price_per_unit": "100"},
    ]
    reference = {
        "customers": {
            "C1": {"name": "Alice",   "tier": "bronze"},
            "C2": {"name": "Bob",     "tier": "silver"},
            "C3": {"name": "Charlie", "tier": "gold"},
        },
        "products": {"P1": {"category": "x", "taxable": False}},
    }
    out = compute_invoices(orders, reference)
    # bronze: discount 0,    final = 100
    # silver: discount 5,    final = 95
    # gold:   discount 10,   final = 90
    discounts = {row[1]: row[3] for row in out}
    finals = {row[1]: row[5] for row in out}
    assert discounts == {"Alice": 0.0, "Bob": 5.0, "Charlie": 10.0}
    assert finals == {"Alice": 100.0, "Bob": 95.0, "Charlie": 90.0}


def test_end_to_end_taxable_and_non_taxable():
    orders = [
        {"order_id": "O1", "customer_id": "C1", "product_id": "P1",
         "quantity": "1", "price_per_unit": "100"},
        {"order_id": "O2", "customer_id": "C1", "product_id": "P2",
         "quantity": "1", "price_per_unit": "100"},
    ]
    reference = {
        "customers": {"C1": {"name": "Alice", "tier": "bronze"}},
        "products": {
            "P1": {"category": "taxed",   "taxable": True},
            "P2": {"category": "untaxed", "taxable": False},
        },
    }
    out = compute_invoices(orders, reference)
    # both bronze (discount 0). P1 taxable -> tax = 20, final = 120.
    # P2 non-taxable -> tax = 0, final = 100.
    taxes = {row[0]: row[4] for row in out}
    finals = {row[0]: row[5] for row in out}
    assert taxes == {"O1": 20.0, "O2": 0.0}
    assert finals == {"O1": 120.0, "O2": 100.0}


def test_end_to_end_secondary_sort_by_order_id():
    orders = [
        {"order_id": "O2", "customer_id": "C1", "product_id": "P1",
         "quantity": "1", "price_per_unit": "10"},
        {"order_id": "O1", "customer_id": "C1", "product_id": "P1",
         "quantity": "1", "price_per_unit": "10"},
    ]
    reference = {
        "customers": {"C1": {"name": "Alice", "tier": "bronze"}},
        "products": {"P1": {"category": "x", "taxable": False}},
    }
    out = compute_invoices(orders, reference)
    # Both Alice; ties broken by order_id ascending -> O1 first.
    assert [r[0] for r in out] == ["O1", "O2"]


def test_end_to_end_unknown_customer_dropped():
    orders = [
        {"order_id": "O1", "customer_id": "C1", "product_id": "P1",
         "quantity": "1", "price_per_unit": "10"},
        {"order_id": "O2", "customer_id": "C99", "product_id": "P1",
         "quantity": "1", "price_per_unit": "10"},
    ]
    reference = {
        "customers": {"C1": {"name": "Alice", "tier": "bronze"}},
        "products": {"P1": {"category": "x", "taxable": False}},
    }
    out = compute_invoices(orders, reference)
    assert [r[0] for r in out] == ["O1"]


def test_end_to_end_unknown_product_dropped():
    orders = [
        {"order_id": "O1", "customer_id": "C1", "product_id": "P1",
         "quantity": "1", "price_per_unit": "10"},
        {"order_id": "O2", "customer_id": "C1", "product_id": "P99",
         "quantity": "1", "price_per_unit": "10"},
    ]
    reference = {
        "customers": {"C1": {"name": "Alice", "tier": "bronze"}},
        "products": {"P1": {"category": "x", "taxable": False}},
    }
    out = compute_invoices(orders, reference)
    assert [r[0] for r in out] == ["O1"]


def test_end_to_end_invalid_order_dropped():
    orders = [
        {"order_id": "O1", "customer_id": "C1", "product_id": "P1",
         "quantity": "1", "price_per_unit": "10"},
        {"order_id": "O2", "customer_id": "C1", "product_id": "P1",
         "quantity": "bad", "price_per_unit": "10"},
    ]
    reference = {
        "customers": {"C1": {"name": "Alice", "tier": "bronze"}},
        "products": {"P1": {"category": "x", "taxable": False}},
    }
    out = compute_invoices(orders, reference)
    assert [r[0] for r in out] == ["O1"]


def test_end_to_end_empty_returns_empty():
    reference = {
        "customers": {"C1": {"name": "Alice", "tier": "bronze"}},
        "products": {"P1": {"category": "x", "taxable": False}},
    }
    assert compute_invoices([], reference) == []
