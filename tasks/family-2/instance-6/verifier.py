"""Verifier test suite for Family 2, Instance 6: process_billing.

Run during a run with: pytest tasks/family-2/instance-6/verifier.py
The runner adds the run's workspace to PYTHONPATH so the imports below
resolve to the agents' deliverables (the sixteen step files plus
pipeline.py).

To validate this verifier against the reference solution locally:

    PYTHONPATH=tasks/family-2/instance-6/solution \\
        .venv/bin/pytest tasks/family-2/instance-6/verifier.py

process_billing is a sixteen-step chain (the H8 doubling of the
eight-step compute_invoices). Steps 1, 2, 5, 7, 9 mirror
compute_invoices; the rest are new (dedupe, region, embargo,
volume surcharge, loyalty credit, taxable base, shipping, final
amount, rank). Rounding is deferred to the final step, so the chain
is deterministic.
"""

from parse import parse
from validate import validate
from dedupe import dedupe
from resolve_customer import resolve_customer
from resolve_product import resolve_product
from filter_embargo import filter_embargo
from compute_line_totals import compute_line_totals
from apply_volume_surcharge import apply_volume_surcharge
from apply_discount import apply_discount
from apply_loyalty_credit import apply_loyalty_credit
from compute_taxable_base import compute_taxable_base
from compute_tax import compute_tax
from apply_shipping import apply_shipping
from compute_final_amount import compute_final_amount
from rank_orders import rank_orders
from format_billing import format_billing
from pipeline import process_billing


# --- helpers ---------------------------------------------------------------

def _order(**kw):
    base = {"order_id": "O1", "customer_id": "C1", "product_id": "P1",
            "quantity": "1", "price_per_unit": "10.0"}
    base.update(kw)
    return base


# --- step 1: parse ---------------------------------------------------------

def test_parse_valid():
    out = parse([_order(quantity="3", price_per_unit="10.0")])
    assert out == [{"order_id": "O1", "customer_id": "C1", "product_id": "P1",
                    "quantity": 3, "price_per_unit": 10.0, "invalid": False}]


def test_parse_bool_quantity_excluded():
    out = parse([_order(quantity=True)])
    assert out[0]["quantity"] is None and out[0]["invalid"] is True


def test_parse_bool_price_excluded():
    out = parse([_order(price_per_unit=True)])
    assert out[0]["price_per_unit"] is None and out[0]["invalid"] is True


def test_parse_missing_marks_invalid():
    raw = {"order_id": "O1", "customer_id": "C1", "product_id": "P1",
           "quantity": "3"}  # price missing
    assert parse([raw])[0]["invalid"] is True


# --- step 2: validate ------------------------------------------------------

def test_validate_drops_invalid_and_key():
    parsed = parse([_order(quantity="2", price_per_unit="5.0")])
    out = validate(parsed)
    assert out == [{"order_id": "O1", "customer_id": "C1", "product_id": "P1",
                    "quantity": 2, "price_per_unit": 5.0}]


def test_validate_drops_zero_quantity():
    parsed = parse([_order(quantity="0")])
    assert validate(parsed) == []


def test_validate_drops_invalid_record():
    parsed = parse([_order(quantity=True)])
    assert validate(parsed) == []


# --- step 3: dedupe --------------------------------------------------------

def test_dedupe_keeps_first():
    recs = [{"order_id": "A", "v": 1}, {"order_id": "A", "v": 2},
            {"order_id": "B", "v": 3}]
    assert dedupe(recs) == [{"order_id": "A", "v": 1}, {"order_id": "B", "v": 3}]


def test_dedupe_no_duplicates():
    recs = [{"order_id": "A"}, {"order_id": "B"}]
    assert dedupe(recs) == recs


# --- step 4: resolve_customer ----------------------------------------------

def test_resolve_customer_attaches():
    recs = [{"order_id": "O1", "customer_id": "C1"}]
    customers = {"C1": {"name": "Alice", "tier": "gold", "region": "azure"}}
    out = resolve_customer(recs, customers)
    assert out[0]["customer_name"] == "Alice"
    assert out[0]["customer_tier"] == "gold"
    assert out[0]["customer_region"] == "azure"


def test_resolve_customer_drops_unknown():
    recs = [{"order_id": "O1", "customer_id": "CX"}]
    assert resolve_customer(recs, {}) == []


# --- step 5: resolve_product -----------------------------------------------

def test_resolve_product_attaches():
    recs = [{"product_id": "P1"}]
    products = {"P1": {"category": "standard", "taxable": True}}
    out = resolve_product(recs, products)
    assert out[0]["product_category"] == "standard"
    assert out[0]["product_taxable"] is True


def test_resolve_product_drops_unknown():
    assert resolve_product([{"product_id": "PX"}], {}) == []


# --- step 6: filter_embargo ------------------------------------------------

def test_filter_embargo_drops_and_keeps():
    recs = [{"customer_region": "azure"}, {"customer_region": "crimson"},
            {"customer_region": "umber"}]
    assert filter_embargo(recs) == [{"customer_region": "azure"}]


# --- step 7: compute_line_totals -------------------------------------------

def test_line_totals():
    recs = [{"quantity": 3, "price_per_unit": 4.0}]
    out = compute_line_totals(recs)
    assert out[0]["line_total"] == 12.0 and isinstance(out[0]["line_total"], float)


# --- step 8: apply_volume_surcharge ----------------------------------------

def test_surcharge_above_threshold():
    out = apply_volume_surcharge([{"quantity": 200, "line_total": 1000.0}])
    assert out[0]["surcharge"] == 20.0


def test_surcharge_at_threshold_is_zero():
    out = apply_volume_surcharge([{"quantity": 100, "line_total": 1000.0}])
    assert out[0]["surcharge"] == 0.0


def test_surcharge_below_threshold_is_zero():
    out = apply_volume_surcharge([{"quantity": 5, "line_total": 50.0}])
    assert out[0]["surcharge"] == 0.0


# --- step 9: apply_discount ------------------------------------------------

def test_discount_rates():
    recs = [{"customer_tier": "bronze", "line_total": 100.0},
            {"customer_tier": "silver", "line_total": 100.0},
            {"customer_tier": "gold", "line_total": 100.0}]
    out = apply_discount(recs)
    assert [r["discount"] for r in out] == [0.0, 5.0, 10.0]
    assert [r["discount_rate"] for r in out] == [0.00, 0.05, 0.10]


def test_discount_drops_unknown_tier():
    assert apply_discount([{"customer_tier": "platinum", "line_total": 100.0}]) == []


# --- step 10: apply_loyalty_credit -----------------------------------------

def test_loyalty_gold_high_value():
    out = apply_loyalty_credit([{"customer_tier": "gold", "line_total": 2000.0}])
    assert out[0]["loyalty_credit"] == 20.0


def test_loyalty_gold_at_threshold():
    out = apply_loyalty_credit([{"customer_tier": "gold", "line_total": 1000.0}])
    assert out[0]["loyalty_credit"] == 10.0


def test_loyalty_gold_below_threshold_zero():
    out = apply_loyalty_credit([{"customer_tier": "gold", "line_total": 999.0}])
    assert out[0]["loyalty_credit"] == 0.0


def test_loyalty_non_gold_zero():
    out = apply_loyalty_credit([{"customer_tier": "silver", "line_total": 5000.0}])
    assert out[0]["loyalty_credit"] == 0.0


# --- step 11: compute_taxable_base -----------------------------------------

def test_taxable_base():
    recs = [{"line_total": 2000.0, "surcharge": 40.0, "discount": 200.0,
             "loyalty_credit": 20.0}]
    assert compute_taxable_base(recs)[0]["taxable_base"] == 1820.0


# --- step 12: compute_tax --------------------------------------------------

def test_tax_taxable():
    out = compute_tax([{"taxable_base": 1820.0, "product_taxable": True}])
    assert out[0]["tax"] == 364.0


def test_tax_non_taxable_zero():
    out = compute_tax([{"taxable_base": 1820.0, "product_taxable": False}])
    assert out[0]["tax"] == 0.0


# --- step 13: apply_shipping -----------------------------------------------

def test_shipping_per_category():
    recs = [{"product_category": "standard"}, {"product_category": "bulky"},
            {"product_category": "digital"}]
    assert [r["shipping"] for r in apply_shipping(recs)] == [5.0, 15.0, 0.0]


def test_shipping_unknown_category_default():
    out = apply_shipping([{"product_category": "exotic"}])
    assert out[0]["shipping"] == 5.0


# --- step 14: compute_final_amount -----------------------------------------

def test_final_amount():
    recs = [{"taxable_base": 1820.0, "tax": 364.0, "shipping": 5.0}]
    assert compute_final_amount(recs)[0]["final_amount"] == 2189.0


# --- step 15: rank_orders --------------------------------------------------

def test_rank_orders_desc_and_tiebreak():
    recs = [{"order_id": "B", "final_amount": 10.0},
            {"order_id": "A", "final_amount": 10.0},
            {"order_id": "C", "final_amount": 50.0}]
    out = rank_orders(recs)
    assert [(r["order_id"], r["rank"]) for r in out] == [
        ("C", 1), ("A", 2), ("B", 3)]


def test_rank_uses_unrounded_final():
    # 10.006 and 10.014 both round to 10.01, but ranking is on the UNROUNDED
    # value, so the larger unrounded amount (B) ranks first. An implementation
    # that ranks on the rounded value would tie and put A first.
    recs = [{"order_id": "A", "final_amount": 10.006},
            {"order_id": "B", "final_amount": 10.014}]
    out = rank_orders(recs)
    assert [(r["order_id"], r["rank"]) for r in out] == [("B", 1), ("A", 2)]


# --- step 16: format_billing -----------------------------------------------

def test_format_billing_shape_and_rounding():
    recs = [{"order_id": "O1", "customer_name": "Alice",
             "final_amount": 8.996, "rank": 1}]
    assert format_billing(recs) == [("O1", "Alice", 9.0, 1)]


def test_format_billing_preserves_order():
    recs = [{"order_id": "B", "customer_name": "Bob", "final_amount": 1.0,
             "rank": 1},
            {"order_id": "A", "customer_name": "Al", "final_amount": 2.0,
             "rank": 2}]
    out = format_billing(recs)
    assert [t[0] for t in out] == ["B", "A"]


# --- integration: process_billing ------------------------------------------

_REF = {
    "customers": {
        "C1": {"name": "Alice", "tier": "gold", "region": "azure"},
        "C2": {"name": "Bob", "tier": "silver", "region": "azure"},
        "C3": {"name": "Cara", "tier": "gold", "region": "crimson"},
    },
    "products": {
        "P1": {"category": "standard", "taxable": True},
        "P2": {"category": "digital", "taxable": False},
    },
}


def test_integration_full_chain_and_ranking():
    orders = [
        _order(order_id="O3", customer_id="C1", product_id="P1",
               quantity="200", price_per_unit="10.0"),
        _order(order_id="O1", customer_id="C2", product_id="P2",
               quantity="5", price_per_unit="4.0"),
    ]
    out = process_billing(orders, _REF)
    assert out == [("O3", "Alice", 2189.0, 1), ("O1", "Bob", 19.0, 2)]


def test_integration_dedupe_drops_repeat():
    orders = [
        _order(order_id="O1", customer_id="C2", product_id="P2",
               quantity="5", price_per_unit="4.0"),
        _order(order_id="O1", customer_id="C2", product_id="P2",
               quantity="9", price_per_unit="4.0"),
    ]
    out = process_billing(orders, _REF)
    assert len(out) == 1 and out[0][0] == "O1" and out[0][2] == 19.0


def test_integration_embargo_drop():
    orders = [_order(order_id="O2", customer_id="C3", product_id="P1",
                     quantity="1", price_per_unit="10.0")]
    assert process_billing(orders, _REF) == []


def test_integration_invalid_drop():
    orders = [_order(order_id="O4", customer_id="C1", product_id="P1",
                     quantity=True, price_per_unit="10.0")]
    assert process_billing(orders, _REF) == []


def test_integration_unknown_customer_and_product_drop():
    bad_cust = [_order(order_id="O5", customer_id="CX")]
    bad_prod = [_order(order_id="O6", product_id="PX")]
    assert process_billing(bad_cust, _REF) == []
    assert process_billing(bad_prod, _REF) == []


def test_integration_rounding():
    # bronze, taxable standard, price 3.33 qty 1: line 3.33, base 3.33,
    # tax 0.20*3.33=0.666, shipping 5 -> final 8.996 -> 9.0
    orders = [_order(order_id="O7", customer_id="C4", product_id="P1",
                     quantity="1", price_per_unit="3.33")]
    ref = {"customers": {"C4": {"name": "Dee", "tier": "bronze",
                                "region": "azure"}},
           "products": {"P1": {"category": "standard", "taxable": True}}}
    out = process_billing(orders, ref)
    assert out == [("O7", "Dee", 9.0, 1)]


def test_integration_empty():
    assert process_billing([], _REF) == []
