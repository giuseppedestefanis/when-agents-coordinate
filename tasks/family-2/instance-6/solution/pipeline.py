"""Reference implementation of `pipeline.process_billing`.

Wires the sixteen step functions in order. The agents' deliverable is
this file plus the sixteen step modules; the reference produces the
same seventeen files. reference = {"customers": {...}, "products":
{...}}.
"""
from __future__ import annotations

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


def process_billing(orders, reference):
    customers = reference["customers"]
    products = reference["products"]
    records = parse(orders)
    records = validate(records)
    records = dedupe(records)
    records = resolve_customer(records, customers)
    records = resolve_product(records, products)
    records = filter_embargo(records)
    records = compute_line_totals(records)
    records = apply_volume_surcharge(records)
    records = apply_discount(records)
    records = apply_loyalty_credit(records)
    records = compute_taxable_base(records)
    records = compute_tax(records)
    records = apply_shipping(records)
    records = compute_final_amount(records)
    records = rank_orders(records)
    return format_billing(records)
