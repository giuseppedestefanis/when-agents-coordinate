"""The structured task library.

Each task in the library is a task encoded as structured data: the
function identity and the component blocks. The library is the single source
of truth for the task content used by the generator.

The library holds:

  - process_orders (Family 1, four components): the worked example of the
    Family 1 pilot. Design at memory/tasks/family-1/instance-1.md;
    runnable artefacts at tasks/family-1/instance-1/. The validation
    component carries a "lenient" variant for conflicting distributions.

  - summarise_transactions (Family 2, four step components): the worked
    example shared across Family 2 Instances 1, 3 and 5. Design at
    memory/tasks/family-2/instance-1.md; runnable artefacts at
    tasks/family-2/instance-1/. The validate component carries a
    "strict" variant (amount > 0 instead of amount >= 0; B2 in the
    Instance 5 conflict).

  - compute_invoices (Family 2, eight step components): the longer
    worked example used by Instance 2. Design at
    memory/tasks/family-2/instance-2.md; runnable artefacts at
    tasks/family-2/instance-2/.

  - summarise_transactions_v2 (Family 2, four step components): the
    Instance 4 variant with the non-local CATEGORY_ORDER dependency
    between step 1 and step 4. Design at
    memory/tasks/family-2/instance-4.md; runnable artefacts at
    tasks/family-2/instance-4/.
"""

from __future__ import annotations

from agent_comms.task_generator.model import Component, FAMILY_2, Task

_SIGNATURE = """\
The function is process_orders(orders, config).

orders is a list of order dicts. Each order dict has the fields id, customer,
amount and quantity. config is a configuration dict.

The function returns a single summary dict with exactly four keys:

  processed: a list of dicts. Each dict has exactly three keys: id (a string),
             customer (a string) and final_amount (a float).
  count:     an int, the number of valid orders.
  total:     a float, the sum of every final_amount in processed, rounded to
             two decimal places. It is 0.0 when processed is empty, and is
             always returned as a float, including when its value is a whole
             number.
  rejected:  an int, the number of invalid orders.

An order that is valid contributes one entry to processed and is counted in
count. An order that is invalid is counted in rejected and does not appear in
processed. Whether an order is valid, how final_amount is computed, and the
order of entries in processed are defined by other parts of the specification.

If orders is an empty list, the function returns
{"processed": [], "count": 0, "total": 0.0, "rejected": 0}."""

_VALIDATION = """\
An order dict has the fields id, customer, amount and quantity.

An order is valid if and only if all of the following hold:

  - id is a non-empty string.
  - customer is a non-empty string.
  - amount is an int or a float and is greater than or equal to 0.
  - quantity is an int and is greater than 0.

An order that fails any one of these checks is invalid. Invalid orders are
excluded from the processed result and counted separately. Valid orders are
carried forward for discount and sorting."""

_VALIDATION_LENIENT = """\
An order dict has the fields id, customer, amount and quantity.

An order is valid if and only if all of the following hold:

  - id is a non-empty string.
  - customer is a non-empty string.
  - amount is an int or a float and is greater than or equal to 0.
  - quantity is an int and is greater than or equal to 0.

An order that fails any one of these checks is invalid. Invalid orders are
excluded from the processed result and counted separately. Valid orders are
carried forward for discount and sorting."""

_DISCOUNT = """\
Each valid order has a final_amount computed from its amount field, using the
config keys bulk_threshold, bulk_discount, loyalty_customers and
loyalty_discount.

Start with final_amount equal to the order's amount.

  - If the order's quantity is greater than or equal to config["bulk_threshold"],
    multiply final_amount by (1 - config["bulk_discount"]).
  - If the order's customer is in the list config["loyalty_customers"],
    multiply final_amount by (1 - config["loyalty_discount"]).

Both discounts may apply to the same order. When they do, they compound
multiplicatively. After applying whichever discounts apply, round final_amount
to two decimal places."""

_SORTING = """\
The processed list of valid orders is ordered using the config key sort_by.

config["sort_by"] is either the string "amount" or the string "id".

  - If sort_by is "amount", order processed by each entry's final_amount in
    ascending order. Where two entries have the same final_amount, break the
    tie by id in ascending order.
  - If sort_by is "id", order processed by id in ascending order."""


PROCESS_ORDERS = Task(
    task_id="process_orders",
    function_name="process_orders",
    solution_path="solution.py",
    components=[
        Component("Signature", _SIGNATURE),
        Component("Validation rules", _VALIDATION,
                  variants={"lenient": _VALIDATION_LENIENT}),
        Component("Discount rule", _DISCOUNT),
        Component("Sorting rule", _SORTING),
    ],
    verifier_path="tasks/family-1/instance-1/verifier.py",
    reference_solution_path="tasks/family-1/instance-1/solution.py",
)


# --- Family 2 ----------------------------------------------------------------
# Family 2 tasks are chains of step functions. Each component is one step:
# its specification text and the file the step is delivered in.
# `solution_path` is the pipeline file the verifier imports from; each step
# component has its own `deliverable_path`. The team_signature is rendered
# verbatim into the prompt's signature block.

# --- summarise_transactions (Instances 1, 3, 5) -----------------------------

_ST_TEAM_SIGNATURE = """\
    pipeline.summarise_transactions(records: list[dict])
        -> list[tuple[str, float]]"""

_ST_PARSE = """\
The function is parse(records: list[dict]) -> list[dict].

Input: a list of dictionaries with at most three string keys, "date", "amount"
and "category". Any key may be absent; values may be of any type.

Output: a list of the same length as the input. Each element is a dictionary
with exactly four keys:

  - "date": a datetime.date, or None if the input's "date" was missing or
    could not be parsed as YYYY-MM-DD.
  - "amount": a float, or None if the input's "amount" was missing or could
    not be coerced. bool values count as missing because bool is a subclass
    of int and would otherwise pass the float coercion; bool must be
    explicitly excluded before coercing.
  - "category": a str with leading and trailing whitespace removed and
    converted to lowercase, or None if the input's "category" was missing or
    was not a string.
  - "invalid": a bool. True if any of the three coercions failed
    (any of the first three fields ended as None), False otherwise.

Edge cases:
  - Empty input returns an empty list.
  - Missing key: treated as a coercion failure for that field.
  - bool amount is rejected: a record with True or False in the amount
    field has amount set to None and invalid set to True.
  - Whitespace category: "  Groceries  " becomes "groceries"."""

_ST_VALIDATE = """\
The function is validate(parsed: list[dict]) -> list[dict].

Input: the output of the parse step.

Output: a list of dictionaries containing the records that pass validation.
Each surviving dictionary has exactly three keys: "date" (a datetime.date),
"amount" (a float) and "category" (a str). The "invalid" flag is dropped.

A record passes validation if and only if all of the following hold:

  - Its "invalid" flag is False.
  - Its "amount" is greater than or equal to zero (a zero amount is valid).
  - Its "category" is one of the strings in the allowed set
    {"groceries", "transport", "rent", "utilities", "entertainment"}.

Edge cases:
  - Empty input returns an empty list.
  - amount of exactly zero is valid (this is the boundary; the spec says
    greater than or equal to zero).
  - Allowed-set membership is by exact match against the lowercase strings
    in the set. Capitalisation is already normalised by the parse step."""

_ST_VALIDATE_STRICT = """\
The function is validate(parsed: list[dict]) -> list[dict].

Input: the output of the parse step.

Output: a list of dictionaries containing the records that pass validation.
Each surviving dictionary has exactly three keys: "date" (a datetime.date),
"amount" (a float) and "category" (a str). The "invalid" flag is dropped.

A record passes validation if and only if all of the following hold:

  - Its "invalid" flag is False.
  - Its "amount" is strictly greater than zero (a zero amount is invalid).
  - Its "category" is one of the strings in the allowed set
    {"groceries", "transport", "rent", "utilities", "entertainment"}.

Edge cases:
  - Empty input returns an empty list.
  - amount of exactly zero is invalid (this is the boundary).
  - Allowed-set membership is by exact match."""

_ST_AGGREGATE = """\
The function is aggregate(validated: list[dict]) -> dict[str, float].

Input: the output of the validate step.

Output: a dictionary mapping YYYY-MM strings (the year-month portion of each
record's date) to the raw sum of that month's amounts. The sum is the
unrounded float result of summing the matching records' amount values. The
dictionary's keys are not ordered.

Edge cases:
  - Empty input returns the empty dictionary {}.
  - Single month: returns a one-entry dictionary.
  - Multiple categories in the same month are summed together; aggregation
    is by month only, not by month and category."""

_ST_FORMAT = """\
The function is format_output(totals: dict[str, float])
    -> list[tuple[str, float]].

Input: the output of the aggregate step.

Output: a list of (month, total) tuples sorted by month in ascending order.
Each total is the corresponding input value rounded to two decimal places by
round(value, 2), then explicitly cast to float (so that whole-number totals
are reported as float and not as int).

Edge cases:
  - Empty input returns the empty list [].
  - The output total must always be a float, including when round(value, 2)
    would return an int. This is enforced by the explicit cast.
  - Sort is by lexicographic order on the YYYY-MM string, which coincides
    with chronological order for valid year-month strings, including
    across year boundaries (because the format is fixed-width)."""

SUMMARISE_TRANSACTIONS = Task(
    task_id="summarise_transactions",
    function_name="summarise_transactions",
    solution_path="pipeline.py",
    family=FAMILY_2,
    team_signature=_ST_TEAM_SIGNATURE,
    components=[
        Component("Step: parse", _ST_PARSE, deliverable_path="parse.py"),
        Component("Step: validate", _ST_VALIDATE,
                  variants={"strict": _ST_VALIDATE_STRICT},
                  deliverable_path="validate.py"),
        Component("Step: aggregate", _ST_AGGREGATE,
                  deliverable_path="aggregate.py"),
        Component("Step: format_output", _ST_FORMAT,
                  deliverable_path="format_output.py"),
    ],
    verifier_path="tasks/family-2/instance-1/verifier.py",
    reference_solution_path="tasks/family-2/instance-1/solution/",
)


# --- compute_invoices (Instance 2) ------------------------------------------

_CI_TEAM_SIGNATURE = """\
    pipeline.compute_invoices(orders: list[dict], reference: dict)
        -> list[tuple]"""

_CI_PARSE = """\
The function is parse(orders: list[dict]) -> list[dict].

Input: a list of dictionaries with at most five string keys: "order_id",
"customer_id", "product_id", "quantity", "price_per_unit". Any key may be
absent; values may be of any type.

Output: a list of the same length as the input. Each element has exactly six
keys:

  - "order_id": a str, or None if missing or non-string.
  - "customer_id": a str, or None.
  - "product_id": a str, or None.
  - "quantity": an int, or None if missing or not coercible to a non-negative
    integer. bool values are excluded (the same trap as in the
    summarise_transactions task).
  - "price_per_unit": a float, or None. bool values are excluded.
  - "invalid": a bool, True if any of the first five fields is None."""

_CI_VALIDATE = """\
The function is validate(parsed: list[dict]) -> list[dict].

Input: the output of the parse step.

Output: surviving records, with the invalid flag dropped. A record survives
if and only if its invalid flag is False, its quantity is greater than zero,
and its price_per_unit is greater than or equal to zero."""

_CI_RESOLVE_CUSTOMER = """\
The function is resolve_customer(records: list[dict], customers: dict)
    -> list[dict].

Input: the output of the validate step, plus a customers lookup of the shape
{customer_id: {"name": str, "tier": str}}. tier is one of "bronze", "silver",
"gold".

Output: each input record extended with two new keys:

  - "customer_name": a str taken from the lookup.
  - "customer_tier": a str taken from the lookup.

Records whose customer_id is not in the lookup are dropped (unknown customers
are not invoiceable in this task)."""

_CI_RESOLVE_PRODUCT = """\
The function is resolve_product(records: list[dict], products: dict)
    -> list[dict].

Input: the output of the resolve_customer step, plus a products lookup of
the shape {product_id: {"category": str, "taxable": bool}}.

Output: each input record extended with two new keys:

  - "product_category": a str taken from the lookup.
  - "product_taxable": a bool taken from the lookup.

Records whose product_id is not in the lookup are dropped."""

_CI_LINE_TOTALS = """\
The function is compute_line_totals(records: list[dict]) -> list[dict].

Input: the output of the resolve_product step.

Output: each input record extended with one new key, "line_total", the float
quantity * price_per_unit. No rounding at this step; rounding is deferred
to the formatting step to avoid compounding rounding errors through the
chain."""

_CI_DISCOUNT = """\
The function is apply_discount(records: list[dict]) -> list[dict].

Input: the output of the compute_line_totals step.

Output: each input record extended with two new keys:

  - "discount_rate": a float, the tier-specific rate: 0.00 for "bronze",
    0.05 for "silver", 0.10 for "gold". Records whose customer_tier is none
    of these are dropped (defensive case).
  - "discount": a float, the unrounded line_total * discount_rate."""

_CI_TAX = """\
The function is compute_tax(records: list[dict]) -> list[dict].

Input: the output of the apply_discount step.

Output: each input record extended with one new key, "tax", computed on the
after-discount amount at twenty per cent for taxable products and zero per
cent for non-taxable:

    after_discount = line_total - discount
    tax_rate       = 0.20 if product_taxable else 0.00
    tax            = after_discount * tax_rate

Unrounded."""

_CI_FORMAT = """\
The function is format_invoices(records: list[dict]) -> list[tuple].

Input: the output of the compute_tax step.

Output: a list of (order_id, customer_name, line_total, discount, tax,
final_amount) tuples, sorted by customer_name in ascending order.
final_amount is computed as line_total - discount + tax. line_total,
discount, tax and final_amount are each rounded to two decimal places by
round(value, 2) and cast to float, so that whole-number amounts are reported
as float and not as int.

If two records share a customer_name, the secondary sort key is order_id
ascending."""

COMPUTE_INVOICES = Task(
    task_id="compute_invoices",
    function_name="compute_invoices",
    solution_path="pipeline.py",
    family=FAMILY_2,
    team_signature=_CI_TEAM_SIGNATURE,
    components=[
        Component("Step: parse", _CI_PARSE, deliverable_path="parse.py"),
        Component("Step: validate", _CI_VALIDATE,
                  deliverable_path="validate.py"),
        Component("Step: resolve_customer", _CI_RESOLVE_CUSTOMER,
                  deliverable_path="resolve_customer.py"),
        Component("Step: resolve_product", _CI_RESOLVE_PRODUCT,
                  deliverable_path="resolve_product.py"),
        Component("Step: compute_line_totals", _CI_LINE_TOTALS,
                  deliverable_path="compute_line_totals.py"),
        Component("Step: apply_discount", _CI_DISCOUNT,
                  deliverable_path="apply_discount.py"),
        Component("Step: compute_tax", _CI_TAX,
                  deliverable_path="compute_tax.py"),
        Component("Step: format_invoices", _CI_FORMAT,
                  deliverable_path="format_invoices.py"),
    ],
    verifier_path="tasks/family-2/instance-2/verifier.py",
    reference_solution_path="tasks/family-2/instance-2/solution/",
)


# --- summarise_transactions_v2 (Instance 4) ---------------------------------
# Step 1's spec additionally defines CATEGORY_ORDER, the constant the step 4
# spec must use as the secondary sort key. The agent holding step 4 must
# discover and obtain CATEGORY_ORDER through coordination with whoever holds
# step 1.

_ST2_TEAM_SIGNATURE = """\
    pipeline.summarise_transactions_v2(records: list[dict])
        -> list[tuple[str, str, float]]"""

_ST2_PARSE = _ST_PARSE + """

In addition, this step's specification DEFINES the constant

    CATEGORY_ORDER = ("groceries", "transport", "rent",
                      "utilities", "entertainment")

CATEGORY_ORDER is the canonical category ordering for the v2 task. It is
NOT part of the parse function's runtime behaviour; it is part of the task's
specification, written down in this step's specification because parse is
the natural home for category definitions. There is exactly one place in
the specification where CATEGORY_ORDER is defined: this place."""

_ST2_AGGREGATE = """\
The function is aggregate(validated: list[dict])
    -> dict[tuple[str, str], float].

Input: the output of the validate step.

Output: a dictionary mapping (month, category) tuples to the raw sum of that
group's amounts. month is the year-month string of the record's date;
category is the record's category string. Sum unrounded. The dictionary's
keys are not ordered.

Edge cases:
  - Empty input returns the empty dictionary {}.
  - Unlike the v1 task, aggregation is by (month, category): two records in
    the same month with different categories appear as two separate
    dictionary entries."""

_ST2_FORMAT = """\
The function is format_output(totals: dict[tuple[str, str], float])
    -> list[tuple[str, str, float]].

Input: the output of the aggregate step.

Output: a list of (month, category, total) tuples sorted by two keys:

  1. Primary key: month ascending (lexicographic on YYYY-MM, which coincides
     with chronological order on valid year-month strings).
  2. Secondary key: category in the order given by CATEGORY_ORDER.

Each total is the corresponding input value rounded to two decimal places
by round(value, 2), then explicitly cast to float.

CATEGORY_ORDER is a tuple of category names defined in another step's
specification (not in this one). The agent who holds this step must obtain
its value through coordination; CATEGORY_ORDER cannot be guessed because
it does not coincide with alphabetical sort.

Edge cases:
  - Empty input returns the empty list [].
  - The output total must always be a float, including when round(value, 2)
    would return an int."""

SUMMARISE_TRANSACTIONS_V2 = Task(
    task_id="summarise_transactions_v2",
    function_name="summarise_transactions_v2",
    solution_path="pipeline.py",
    family=FAMILY_2,
    team_signature=_ST2_TEAM_SIGNATURE,
    components=[
        Component("Step: parse", _ST2_PARSE, deliverable_path="parse.py"),
        Component("Step: validate", _ST_VALIDATE,
                  deliverable_path="validate.py"),
        Component("Step: aggregate", _ST2_AGGREGATE,
                  deliverable_path="aggregate.py"),
        Component("Step: format_output", _ST2_FORMAT,
                  deliverable_path="format_output.py"),
    ],
    verifier_path="tasks/family-2/instance-4/verifier.py",
    reference_solution_path="tasks/family-2/instance-4/solution/",
)


# --- process_billing (Instance 6, H8 16-step chain) -------------------------
# The natural doubling of compute_invoices (8 steps) to sixteen, so that full
# decomposition lands at n=16. Pure data-flow chain (no ST2-style non-local
# constant); rounding deferred to the final step. Steps parse/validate/
# resolve_product/compute_line_totals/apply_discount mirror compute_invoices.

_PB_TEAM_SIGNATURE = """\
    pipeline.process_billing(orders: list[dict], reference: dict)
        -> list[tuple]"""

_PB_PARSE = _CI_PARSE

_PB_VALIDATE = _CI_VALIDATE

_PB_DEDUPE = """\
The function is dedupe(records: list[dict]) -> list[dict].

Input: the output of the validate step.

Output: the same records with any record whose order_id has already
appeared earlier in the list removed. Keep the first occurrence of each
order_id and preserve the input order."""

_PB_RESOLVE_CUSTOMER = """\
The function is resolve_customer(records: list[dict], customers: dict)
    -> list[dict].

Input: the output of the dedupe step, plus a customers lookup of the shape
{customer_id: {"name": str, "tier": str, "region": str}}. tier is one of
"bronze", "silver", "gold".

Output: each record extended with three new keys:

  - "customer_name": a str taken from the lookup.
  - "customer_tier": a str taken from the lookup.
  - "customer_region": a str taken from the lookup.

Records whose customer_id is not in the lookup are dropped."""

_PB_RESOLVE_PRODUCT = """\
The function is resolve_product(records: list[dict], products: dict)
    -> list[dict].

Input: the output of the resolve_customer step, plus a products lookup of
the shape {product_id: {"category": str, "taxable": bool}}.

Output: each record extended with "product_category" (str) and
"product_taxable" (bool) from the lookup. Records whose product_id is not
in the lookup are dropped."""

_PB_FILTER_EMBARGO = """\
The function is filter_embargo(records: list[dict]) -> list[dict].

Input: the output of the resolve_product step.

This step's specification DEFINES the module-level constant

    EMBARGOED_REGIONS = ("crimson", "umber")

Output: the records whose customer_region is NOT in EMBARGOED_REGIONS;
records in an embargoed region are dropped."""

_PB_LINE_TOTALS = """\
The function is compute_line_totals(records: list[dict]) -> list[dict].

Input: the output of the filter_embargo step.

Output: each record extended with one new key, "line_total", the float
quantity * price_per_unit. No rounding (rounding is deferred to the final
step to avoid compounding errors through the chain)."""

_PB_SURCHARGE = """\
The function is apply_volume_surcharge(records: list[dict]) -> list[dict].

Input: the output of the compute_line_totals step.

Output: each record extended with one new key, "surcharge", the float
0.02 * line_total when quantity > 100, and 0.0 otherwise. Unrounded."""

_PB_DISCOUNT = """\
The function is apply_discount(records: list[dict]) -> list[dict].

Input: the output of the apply_volume_surcharge step.

Output: each record extended with two new keys:

  - "discount_rate": a float, the tier-specific rate: 0.00 for "bronze",
    0.05 for "silver", 0.10 for "gold". Records whose customer_tier is none
    of these are dropped.
  - "discount": a float, the unrounded line_total * discount_rate."""

_PB_LOYALTY = """\
The function is apply_loyalty_credit(records: list[dict]) -> list[dict].

Input: the output of the apply_discount step.

Output: each record extended with one new key, "loyalty_credit", the float
0.01 * line_total when customer_tier is "gold" AND line_total >= 1000, and
0.0 otherwise. Unrounded."""

_PB_TAXABLE_BASE = """\
The function is compute_taxable_base(records: list[dict]) -> list[dict].

Input: the output of the apply_loyalty_credit step.

Output: each record extended with one new key, "taxable_base", the float

    line_total + surcharge - discount - loyalty_credit

Unrounded."""

_PB_TAX = """\
The function is compute_tax(records: list[dict]) -> list[dict].

Input: the output of the compute_taxable_base step.

Output: each record extended with one new key, "tax", the float
taxable_base * 0.20 for taxable products (product_taxable True) and
taxable_base * 0.00 otherwise. Unrounded."""

_PB_SHIPPING = """\
The function is apply_shipping(records: list[dict]) -> list[dict].

Input: the output of the compute_tax step.

This step's specification DEFINES the module-level constant

    SHIPPING_FEES = {"standard": 5.0, "bulky": 15.0, "digital": 0.0}

Output: each record extended with one new key, "shipping", the fee for the
record's product_category taken from SHIPPING_FEES, or the default 5.0 when
the category is not a key of SHIPPING_FEES."""

_PB_FINAL = """\
The function is compute_final_amount(records: list[dict]) -> list[dict].

Input: the output of the apply_shipping step.

Output: each record extended with one new key, "final_amount", the float

    taxable_base + tax + shipping

Unrounded."""

_PB_RANK = """\
The function is rank_orders(records: list[dict]) -> list[dict].

Input: the output of the compute_final_amount step.

Output: the records sorted by final_amount DESCENDING, with order_id
ASCENDING as the tie-breaker, each extended with one new key, "rank", the
1-based integer position in that sorted order. Return the records in the
ranked order. Rank on the unrounded final_amount."""

_PB_FORMAT = """\
The function is format_billing(records: list[dict]) -> list[tuple].

Input: the output of the rank_orders step (already in ranked order).

Output: a list of (order_id, customer_name, final_amount, rank) tuples in
the same order as the input. final_amount is rounded to two decimal places
by round(value, 2) and cast to float, so whole-number amounts are reported
as float and not as int."""

PROCESS_BILLING = Task(
    task_id="process_billing",
    function_name="process_billing",
    solution_path="pipeline.py",
    family=FAMILY_2,
    team_signature=_PB_TEAM_SIGNATURE,
    components=[
        Component("Step: parse", _PB_PARSE, deliverable_path="parse.py"),
        Component("Step: validate", _PB_VALIDATE,
                  deliverable_path="validate.py"),
        Component("Step: dedupe", _PB_DEDUPE, deliverable_path="dedupe.py"),
        Component("Step: resolve_customer", _PB_RESOLVE_CUSTOMER,
                  deliverable_path="resolve_customer.py"),
        Component("Step: resolve_product", _PB_RESOLVE_PRODUCT,
                  deliverable_path="resolve_product.py"),
        Component("Step: filter_embargo", _PB_FILTER_EMBARGO,
                  deliverable_path="filter_embargo.py"),
        Component("Step: compute_line_totals", _PB_LINE_TOTALS,
                  deliverable_path="compute_line_totals.py"),
        Component("Step: apply_volume_surcharge", _PB_SURCHARGE,
                  deliverable_path="apply_volume_surcharge.py"),
        Component("Step: apply_discount", _PB_DISCOUNT,
                  deliverable_path="apply_discount.py"),
        Component("Step: apply_loyalty_credit", _PB_LOYALTY,
                  deliverable_path="apply_loyalty_credit.py"),
        Component("Step: compute_taxable_base", _PB_TAXABLE_BASE,
                  deliverable_path="compute_taxable_base.py"),
        Component("Step: compute_tax", _PB_TAX,
                  deliverable_path="compute_tax.py"),
        Component("Step: apply_shipping", _PB_SHIPPING,
                  deliverable_path="apply_shipping.py"),
        Component("Step: compute_final_amount", _PB_FINAL,
                  deliverable_path="compute_final_amount.py"),
        Component("Step: rank_orders", _PB_RANK,
                  deliverable_path="rank_orders.py"),
        Component("Step: format_billing", _PB_FORMAT,
                  deliverable_path="format_billing.py"),
    ],
    verifier_path="tasks/family-2/instance-6/verifier.py",
    reference_solution_path="tasks/family-2/instance-6/solution/",
)


TASKS = {
    PROCESS_ORDERS.task_id: PROCESS_ORDERS,
    SUMMARISE_TRANSACTIONS.task_id: SUMMARISE_TRANSACTIONS,
    COMPUTE_INVOICES.task_id: COMPUTE_INVOICES,
    SUMMARISE_TRANSACTIONS_V2.task_id: SUMMARISE_TRANSACTIONS_V2,
    PROCESS_BILLING.task_id: PROCESS_BILLING,
}


def get_task(task_id: str) -> Task:
    """Return a task from the library by its identifier."""
    if task_id not in TASKS:
        raise KeyError(
            f"unknown task {task_id!r}; available: {sorted(TASKS)}")
    return TASKS[task_id]


def role_names_for(task) -> list:
    """Return the list of addressable role names for a task.

    The role names are the spellings an agent might use to address
    another agent by their step role (rather than by canonical
    agent ID). The list is used by the parser to classify
    `target_kind=role` on the agent-to-agent edges.

    Family 1 tasks have no addressable role names: their component
    labels are "Signature", "Validation rules", etc. — descriptive
    labels not surfaced as addressing tokens in the prompts. So
    Family 1 tasks return [].

    Family 2 tasks return one role name per step component, taken
    from the component's deliverable_path basename (without the
    .py extension). The shared `pipeline.py` file is deliberately
    excluded: by design no single agent owns pipeline.py and
    messages addressing it are ambiguous; they surface as
    TARGET_KIND_UNKNOWN, which is itself a coordination signal
    distinct from per-step role addressing.

    Confirmed with the writer terminal on 2026-05-30.
    """
    if task.family != FAMILY_2:
        return []
    roles = []
    for component in task.components:
        path = component.deliverable_path
        if not path:
            continue
        base = path.rsplit("/", 1)[-1]
        if base.endswith(".py"):
            base = base[:-3]
        # Exclude the shared pipeline file: it is the by-design
        # unassigned composition slot and addressing it does not
        # name a specific role.
        if base == "pipeline":
            continue
        roles.append(base)
    return roles
