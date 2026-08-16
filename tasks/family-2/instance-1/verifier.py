"""Verifier test suite for Family 2, Instance 1: summarise_transactions.

Run during a run with: pytest tasks/family-2/instance-1/verifier.py
The runner adds the run's workspace to PYTHONPATH so the imports
below resolve to the agents' deliverables (parse.py, validate.py,
aggregate.py, format_output.py, pipeline.py).

To validate this verifier against the reference solution locally:

    PYTHONPATH=tasks/family-2/instance-1/solution \\
        .venv/bin/pytest tasks/family-2/instance-1/verifier.py

This file is the binding test contract for Instance 1. It is also
the binding test contract for Instance 3 (overlap distribution,
same task) and Instance 5 (conflict distribution, same task plus
one additional zero-amount integration test, which is added in
the Instance 5 verifier file). The list below is the union of
Section 5 of memory/tasks/family-2/instance-1.md and the
Instance 1 entries in memory/tasks/family-2/verifier-checklist.md.

Test count: 25 (9 unit + 4 integration listed in instance-1.md;
6 unit + 5 integration added by verifier-checklist.md; 1 boundary
integration test for Instance 5's B2 conflict discrimination,
which passes under Instance 1's canonical spec). The checklist's
test-count table notes the rough target is 22 and that the
committed set is over; that is the intended state. The verifier
is not shown to agents during a run.
"""

from datetime import date

from parse import parse
from validate import validate
from aggregate import aggregate
from format_output import format_output
from pipeline import summarise_transactions


# --- Step 1 (parse) unit tests ---------------------------------------------

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


# --- Step 2 (validate) unit tests ------------------------------------------

def test_validate_drops_invalid():
    out = validate([
        {"date": date(2026, 1, 1), "amount": 1.0,
         "category": "rent", "invalid": True},
    ])
    assert out == []


def test_validate_zero_amount_kept():
    # Boundary: B1 canonical says amount >= 0. Zero is valid.
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


# --- Step 3 (aggregate) unit tests -----------------------------------------

def test_aggregate_groups_by_month():
    recs = [
        {"date": date(2026, 1, 5), "amount": 10.0,
         "category": "rent"},
        {"date": date(2026, 1, 20), "amount": 5.0,
         "category": "rent"},
        {"date": date(2026, 2, 1), "amount": 7.5,
         "category": "rent"},
    ]
    assert aggregate(recs) == {"2026-01": 15.0, "2026-02": 7.5}


def test_aggregate_empty_returns_empty_dict():
    assert aggregate([]) == {}


# --- Step 4 (format_output) unit tests -------------------------------------

def test_format_returns_float_for_whole_number():
    out = format_output({"2026-01": 10})
    assert out == [("2026-01", 10.0)]
    assert isinstance(out[0][1], float)


def test_format_sorts_by_month():
    out = format_output({"2026-02": 1.0, "2026-01": 2.0})
    assert out == [("2026-01", 2.0), ("2026-02", 1.0)]


def test_format_empty_returns_empty_list():
    assert format_output({}) == []


def test_format_rounds_two_decimals():
    # 12.349 -> 12.35 avoids the round-half-to-even ambiguity at
    # the boundary; the test pins two-decimal rounding cleanly.
    out = format_output({"2026-01": 12.349})
    assert out == [("2026-01", 12.35)]


# --- Integration tests -----------------------------------------------------

def test_end_to_end_minimal():
    records = [
        {"date": "2026-01-15", "amount": "12.50",
         "category": "Groceries"},
        {"date": "2026-01-31", "amount": "20.00",
         "category": "Rent"},
    ]
    assert summarise_transactions(records) == [("2026-01", 32.50)]


def test_end_to_end_drops_invalid_keeps_valid():
    records = [
        {"date": "2026-01-15", "amount": "12.50",
         "category": "groceries"},
        {"amount": "20.00", "category": "rent"},               # bad date
        {"date": "2026-01-20", "amount": "luxury",
         "category": "groceries"},                              # bad amount
    ]
    assert summarise_transactions(records) == [("2026-01", 12.50)]


def test_end_to_end_all_invalid_returns_empty():
    records = [
        {"date": "bad", "amount": "x", "category": "?"},
        {},
    ]
    assert summarise_transactions(records) == []


def test_end_to_end_total_is_float_for_whole_number_sum():
    records = [
        {"date": "2026-01-01", "amount": "10",
         "category": "rent"},
        {"date": "2026-01-15", "amount": "20",
         "category": "rent"},
    ]
    out = summarise_transactions(records)
    assert out == [("2026-01", 30.0)]
    assert isinstance(out[0][1], float)


def test_end_to_end_two_months():
    records = [
        {"date": "2026-01-15", "amount": "10.00",
         "category": "rent"},
        {"date": "2026-02-15", "amount": "20.00",
         "category": "rent"},
    ]
    out = summarise_transactions(records)
    assert out == [("2026-01", 10.0), ("2026-02", 20.0)]


def test_end_to_end_multi_category_one_month():
    records = [
        {"date": "2026-01-05", "amount": "10.00",
         "category": "rent"},
        {"date": "2026-01-15", "amount": "5.00",
         "category": "groceries"},
        {"date": "2026-01-25", "amount": "3.50",
         "category": "transport"},
    ]
    # Aggregation is by month only, not by month+category.
    assert summarise_transactions(records) == [("2026-01", 18.50)]


def test_end_to_end_one_category_multi_month():
    records = [
        {"date": "2026-01-15", "amount": "10.00",
         "category": "rent"},
        {"date": "2026-02-15", "amount": "10.00",
         "category": "rent"},
        {"date": "2026-03-15", "amount": "10.00",
         "category": "rent"},
    ]
    out = summarise_transactions(records)
    assert out == [("2026-01", 10.0), ("2026-02", 10.0),
                   ("2026-03", 10.0)]


def test_end_to_end_whitespace_category():
    records = [
        {"date": "2026-01-15", "amount": "10.00",
         "category": "  Rent  "},
    ]
    assert summarise_transactions(records) == [("2026-01", 10.0)]


def test_end_to_end_year_boundary_sort():
    # Pins the edge-case claim that lexicographic order on YYYY-MM
    # coincides with chronological order across year boundaries.
    records = [
        {"date": "2026-01-10", "amount": "20.00",
         "category": "rent"},
        {"date": "2025-12-20", "amount": "10.00",
         "category": "rent"},
    ]
    out = summarise_transactions(records)
    assert out == [("2025-12", 10.0), ("2026-01", 20.0)]


def test_end_to_end_zero_amount_record_included():
    # Boundary test for Instance 5's B1/B2 discrimination. Under
    # B1 (canonical, used by Instance 1 and Instance 3), the
    # zero-amount record survives validate and contributes a
    # month-with-zero-total row to the output. Under B2 (the
    # Instance 5 conflict version where amount > 0), the record
    # is dropped and the month does not appear in the output at
    # all. The single-record input is the discriminating case:
    # B1 produces [("2026-01", 0.0)] and B2 produces []. The
    # test passes for Instances 1 and 3 because they use the
    # canonical spec; it fails for an Instance 5 team that
    # converged on B2.
    records = [
        {"date": "2026-01-15", "amount": "0", "category": "rent"},
    ]
    out = summarise_transactions(records)
    assert out == [("2026-01", 0.0)]
