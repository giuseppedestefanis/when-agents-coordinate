"""Verifier test suite for Family 2, Instance 4: summarise_transactions_v2.

Run during a run with: pytest tasks/family-2/instance-4/verifier.py
The runner adds the run's workspace to PYTHONPATH so the imports
below resolve to the agents' deliverables (parse.py, validate.py,
aggregate.py, format_output.py, pipeline.py).

To validate this verifier against the reference solution locally:

    PYTHONPATH=tasks/family-2/instance-4/solution \\
        .venv/bin/pytest tasks/family-2/instance-4/verifier.py

Test count: 24 (Instance 4 target). Composition:
  - 9 parse and validate tests inherited from Instance 1 (the v2
    task's step 1 and step 2 behaviour is identical to Instance 1).
  - 8 v2-specific unit tests on the modified aggregate and
    format_output steps (the (month, category) grouping and the
    CATEGORY_ORDER secondary sort).
  - 7 integration tests covering the v2 task end to end,
    including the discriminating two-category case from the
    2026-05-29 pilot-review Finding 3.
"""

from datetime import date

from parse import parse
from validate import validate
from aggregate import aggregate
from format_output import format_output
from pipeline import summarise_transactions_v2


# --- Step 1 (parse) unit tests (inherited from Instance 1) -----------------

def test_parse_valid_record():
    out = parse([
        {"date": "2026-01-15", "amount": "12.50",
         "category": "Groceries"},
    ])
    assert out == [{"date": date(2026, 1, 15), "amount": 12.50,
                    "category": "groceries", "invalid": False}]


def test_parse_missing_date_marks_invalid():
    out = parse([{"amount": "5.00", "category": "rent"}])
    assert out[0]["date"] is None
    assert out[0]["invalid"] is True


def test_parse_bool_amount_not_accepted():
    out = parse([
        {"date": "2026-01-15", "amount": True, "category": "rent"},
    ])
    assert out[0]["amount"] is None
    assert out[0]["invalid"] is True


def test_parse_bool_category_rejected():
    out = parse([
        {"date": "2026-01-15", "amount": "5.00", "category": True},
    ])
    assert out[0]["category"] is None
    assert out[0]["invalid"] is True


def test_parse_whitespace_category_normalised():
    out = parse([
        {"date": "2026-01-15", "amount": "5.00",
         "category": "  Groceries  "},
    ])
    assert out[0]["category"] == "groceries"
    assert out[0]["invalid"] is False


# --- Step 2 (validate) unit tests (inherited from Instance 1) --------------

def test_validate_drops_invalid():
    out = validate([
        {"date": date(2026, 1, 1), "amount": 1.0,
         "category": "rent", "invalid": True},
    ])
    assert out == []


def test_validate_zero_amount_kept():
    out = validate([
        {"date": date(2026, 1, 1), "amount": 0.0,
         "category": "rent", "invalid": False},
    ])
    assert len(out) == 1


def test_validate_unknown_category_dropped():
    out = validate([
        {"date": date(2026, 1, 1), "amount": 1.0,
         "category": "luxury", "invalid": False},
    ])
    assert out == []


def test_validate_negative_amount_dropped():
    out = validate([
        {"date": date(2026, 1, 1), "amount": -1.0,
         "category": "rent", "invalid": False},
    ])
    assert out == []


# --- Step 3 (aggregate) v2 unit tests --------------------------------------

def test_aggregate_groups_by_month_and_category():
    recs = [
        {"date": date(2026, 1, 5), "amount": 10.0,
         "category": "rent"},
        {"date": date(2026, 1, 20), "amount": 5.0,
         "category": "rent"},
        {"date": date(2026, 1, 12), "amount": 3.0,
         "category": "groceries"},
    ]
    assert aggregate(recs) == {("2026-01", "rent"): 15.0,
                                ("2026-01", "groceries"): 3.0}


def test_aggregate_empty_returns_empty_dict():
    assert aggregate([]) == {}


# --- Step 4 (format_output) v2 unit tests ----------------------------------

def test_format_orders_categories_by_CATEGORY_ORDER():
    totals = {
        ("2026-01", "rent"):      10.0,
        ("2026-01", "groceries"):  5.0,
        ("2026-01", "transport"):  2.0,
    }
    # CATEGORY_ORDER = ("groceries", "transport", "rent", ...)
    out = format_output(totals)
    assert [t[1] for t in out] == ["groceries", "transport", "rent"]


def test_format_handles_partial_categories():
    # A month containing only some of the CATEGORY_ORDER entries
    # still orders the rows it has by CATEGORY_ORDER.
    totals = {
        ("2026-01", "rent"):          10.0,
        ("2026-01", "entertainment"):  2.0,
    }
    # CATEGORY_ORDER: rent is third, entertainment is fifth.
    # Rent should come first; entertainment second.
    out = format_output(totals)
    assert [t[1] for t in out] == ["rent", "entertainment"]


def test_format_empty_returns_empty_list():
    assert format_output({}) == []


def test_format_rounds_two_decimals():
    out = format_output({("2026-01", "rent"): 12.349})
    assert out == [("2026-01", "rent", 12.35)]


def test_format_returns_float_for_whole_number():
    out = format_output({("2026-01", "rent"): 10})
    assert out == [("2026-01", "rent", 10.0)]
    assert isinstance(out[0][2], float)


def test_format_sorts_by_month():
    totals = {
        ("2026-02", "rent"): 1.0,
        ("2026-01", "rent"): 2.0,
    }
    out = format_output(totals)
    assert [t[0] for t in out] == ["2026-01", "2026-02"]


# --- Integration tests -----------------------------------------------------

def test_end_to_end_two_months_two_categories():
    records = [
        {"date": "2026-01-15", "amount": "10.00",
         "category": "rent"},
        {"date": "2026-01-20", "amount": "5.00",
         "category": "groceries"},
        {"date": "2026-02-01", "amount": "8.00",
         "category": "rent"},
    ]
    out = summarise_transactions_v2(records)
    # 2026-01: groceries before rent per CATEGORY_ORDER.
    # 2026-02: only rent.
    assert out == [
        ("2026-01", "groceries", 5.0),
        ("2026-01", "rent",      10.0),
        ("2026-02", "rent",      8.0),
    ]


def test_end_to_end_single_category_month_sorts_correctly():
    records = [
        {"date": "2026-01-15", "amount": "10.00",
         "category": "rent"},
        {"date": "2026-02-15", "amount": "20.00",
         "category": "groceries"},
    ]
    out = summarise_transactions_v2(records)
    # Each month contains only one category; the per-month sort
    # has nothing to disambiguate.
    assert out == [
        ("2026-01", "rent",      10.0),
        ("2026-02", "groceries", 20.0),
    ]


def test_end_to_end_categories_in_all_five_present():
    records = [
        {"date": "2026-01-01", "amount": "1.00", "category": "rent"},
        {"date": "2026-01-02", "amount": "2.00",
         "category": "entertainment"},
        {"date": "2026-01-03", "amount": "3.00", "category": "transport"},
        {"date": "2026-01-04", "amount": "4.00", "category": "utilities"},
        {"date": "2026-01-05", "amount": "5.00", "category": "groceries"},
    ]
    out = summarise_transactions_v2(records)
    # CATEGORY_ORDER: groceries, transport, rent, utilities,
    # entertainment.
    assert [t[1] for t in out] == [
        "groceries", "transport", "rent", "utilities",
        "entertainment",
    ]


def test_end_to_end_entertainment_before_rent():
    # The discriminating two-category integration case (Finding 3
    # in the 2026-05-29 pilot review). CATEGORY_ORDER places rent
    # third and entertainment fifth -> rent first. Alphabetical
    # would put entertainment first. A team that fell back to the
    # implicit alphabetical sort fails this test; a team that
    # discovered CATEGORY_ORDER passes.
    records = [
        {"date": "2026-01-10", "amount": "10.00",
         "category": "entertainment"},
        {"date": "2026-01-20", "amount": "20.00",
         "category": "rent"},
    ]
    out = summarise_transactions_v2(records)
    assert out == [
        ("2026-01", "rent",          20.0),
        ("2026-01", "entertainment", 10.0),
    ]


def test_end_to_end_empty_returns_empty():
    assert summarise_transactions_v2([]) == []


def test_end_to_end_year_boundary_sort():
    # Parallel to Instance 1's year-boundary test, generalised to
    # the (month, category) output grain.
    records = [
        {"date": "2026-01-10", "amount": "20.00", "category": "rent"},
        {"date": "2025-12-20", "amount": "10.00", "category": "rent"},
    ]
    out = summarise_transactions_v2(records)
    assert out == [
        ("2025-12", "rent", 10.0),
        ("2026-01", "rent", 20.0),
    ]


def test_end_to_end_drops_invalid_keeps_valid():
    records = [
        {"date": "2026-01-15", "amount": "10.00",
         "category": "groceries"},
        {"amount": "20.00", "category": "rent"},               # bad date
        {"date": "2026-01-20", "amount": "luxury",
         "category": "groceries"},                              # bad amount
    ]
    out = summarise_transactions_v2(records)
    assert out == [("2026-01", "groceries", 10.0)]
