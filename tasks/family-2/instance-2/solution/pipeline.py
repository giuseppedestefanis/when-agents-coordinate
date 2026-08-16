"""Reference implementation of `pipeline.compute_invoices`.

Wires the eight step functions in order. The agents' deliverable
is this file plus the eight step modules; the reference produces
the same nine files.
"""

from __future__ import annotations

from parse import parse
from validate import validate
from resolve_customer import resolve_customer
from resolve_product import resolve_product
from compute_line_totals import compute_line_totals
from apply_discount import apply_discount
from compute_tax import compute_tax
from format_invoices import format_invoices


def compute_invoices(orders, reference):
    customers = reference["customers"]
    products = reference["products"]
    return format_invoices(
        compute_tax(
            apply_discount(
                compute_line_totals(
                    resolve_product(
                        resolve_customer(
                            validate(parse(orders)),
                            customers),
                        products)))))
