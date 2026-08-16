"""Verifier test suite for Family 1, Instance 2: build_report.

Run with: pytest tasks/family-1/instance-2/verifier.py
Expects solution.py in the same directory, exposing build_report.

This file is extracted verbatim from section 5 of
memory/tasks/family-1/instance-2.md, which is the design source of truth. It
is not shown to the agents during a run.
"""

from solution import build_report

BASE_SETTINGS = {
    "active_statuses": ["posted", "cleared"],
    "day_range": [10, 20],
    "category_map": {"grocery": "food", "dining": "food", "fuel": "transport"},
    "min_total": 50.0,
    "sort_by": "category",
}


def settings(**overrides):
    """Return a copy of BASE_SETTINGS with the given keys overridden."""
    cfg = dict(BASE_SETTINGS)
    cfg.update(overrides)
    return cfg


def record(id="r", category="food", amount=100, day=15, status="posted"):
    return {"id": id, "category": category, "amount": amount, "day": day,
            "status": status}


# --- Component A: signature and return shape ---------------------------------

def test_return_has_exactly_four_keys():
    result = build_report([record()], settings())
    assert set(result) == {"categories", "record_count", "category_count",
                           "dropped"}


def test_return_field_types():
    result = build_report([record()], settings())
    assert isinstance(result["categories"], list)
    assert isinstance(result["record_count"], int)
    assert isinstance(result["category_count"], int)
    assert isinstance(result["dropped"], int)


def test_category_entry_shape():
    result = build_report([record(category="food", amount=100)], settings())
    entry = result["categories"][0]
    assert set(entry) == {"category", "total"}
    assert isinstance(entry["category"], str)
    assert isinstance(entry["total"], float)


# --- Component B: validation -------------------------------------------------

def test_rejects_empty_id():
    result = build_report([record(id="")], settings())
    assert result["dropped"] == 1
    assert result["record_count"] == 0


def test_rejects_non_string_id():
    result = build_report([record(id=7)], settings())
    assert result["dropped"] == 1


def test_rejects_empty_category():
    result = build_report([record(category="")], settings())
    assert result["dropped"] == 1


def test_rejects_negative_amount():
    result = build_report([record(amount=-1)], settings())
    assert result["dropped"] == 1


def test_rejects_non_int_day():
    result = build_report([record(day=15.5)], settings())
    assert result["dropped"] == 1


def test_rejects_negative_day():
    result = build_report([record(day=-1)], settings())
    assert result["dropped"] == 1


def test_rejects_empty_status():
    result = build_report([record(status="")], settings())
    assert result["dropped"] == 1


def test_accepts_zero_amount():
    result = build_report([record(amount=0)], settings(min_total=0.0))
    assert result["dropped"] == 0
    assert result["record_count"] == 1


# --- Component C: status filter ----------------------------------------------

def test_status_filter_excludes_inactive_status():
    result = build_report([record(status="void")], settings(min_total=0.0))
    assert result["record_count"] == 0
    assert result["dropped"] == 0
    assert result["categories"] == []


def test_status_filter_keeps_active_status():
    result = build_report([record(status="cleared")], settings(min_total=0.0))
    assert result["record_count"] == 1


# --- Component D: day-window filter ------------------------------------------

def test_day_filter_excludes_below_range():
    result = build_report([record(day=9)], settings(min_total=0.0))
    assert result["record_count"] == 0


def test_day_filter_excludes_above_range():
    result = build_report([record(day=21)], settings(min_total=0.0))
    assert result["record_count"] == 0


def test_day_filter_includes_boundaries():
    result = build_report(
        [record(id="lo", day=10), record(id="hi", day=20)],
        settings(min_total=0.0))
    assert result["record_count"] == 2


# --- Component E: category normalisation -------------------------------------

def test_category_normalised_via_map():
    result = build_report([record(category="grocery", amount=100)], settings())
    assert result["categories"][0]["category"] == "food"


def test_unmapped_category_unchanged():
    result = build_report([record(category="toys", amount=100)], settings())
    assert result["categories"][0]["category"] == "toys"


def test_mapped_categories_merge():
    result = build_report(
        [record(id="a", category="grocery", amount=100),
         record(id="b", category="dining", amount=100)],
        settings())
    assert result["category_count"] == 1
    assert result["categories"][0]["category"] == "food"
    assert result["categories"][0]["total"] == 200.0


# --- Component F: aggregation ------------------------------------------------

def test_aggregation_sums_same_category():
    result = build_report(
        [record(id="a", category="toys", amount=30),
         record(id="b", category="toys", amount=70)],
        settings())
    assert result["category_count"] == 1
    assert result["categories"][0]["total"] == 100.0


def test_aggregation_separates_categories():
    result = build_report(
        [record(id="a", category="toys", amount=100),
         record(id="b", category="books", amount=100)],
        settings())
    assert result["category_count"] == 2


# --- Component G: minimum-total threshold ------------------------------------

def test_threshold_drops_category_below_min():
    result = build_report([record(category="toys", amount=49.99)],
                          settings(min_total=50.0))
    assert result["category_count"] == 0
    assert result["categories"] == []


def test_threshold_keeps_category_equal_to_min():
    result = build_report([record(category="toys", amount=50.0)],
                          settings(min_total=50.0))
    assert result["category_count"] == 1


def test_threshold_does_not_reduce_record_count():
    result = build_report([record(category="toys", amount=10)],
                          settings(min_total=50.0))
    assert result["record_count"] == 1
    assert result["category_count"] == 0


# --- Component A: rounding of totals -----------------------------------------

def test_total_rounded_to_two_places():
    result = build_report(
        [record(id="a", category="toys", amount=0.1),
         record(id="b", category="toys", amount=0.2)],
        settings(min_total=0.0))
    assert result["categories"][0]["total"] == 0.3


# --- Component H: sorting ----------------------------------------------------

def test_sort_by_category_ascending():
    result = build_report(
        [record(id="a", category="toys", amount=100),
         record(id="b", category="books", amount=100),
         record(id="c", category="music", amount=100)],
        settings(sort_by="category", min_total=0.0))
    assert [e["category"] for e in result["categories"]] == \
        ["books", "music", "toys"]


def test_sort_by_total_descending():
    result = build_report(
        [record(id="a", category="toys", amount=200),
         record(id="b", category="books", amount=100),
         record(id="c", category="music", amount=300)],
        settings(sort_by="total", min_total=0.0))
    assert [e["category"] for e in result["categories"]] == \
        ["music", "toys", "books"]


def test_sort_by_total_ties_broken_by_category():
    result = build_report(
        [record(id="a", category="toys", amount=100),
         record(id="b", category="books", amount=100),
         record(id="c", category="music", amount=300)],
        settings(sort_by="total", min_total=0.0))
    assert [e["category"] for e in result["categories"]] == \
        ["music", "books", "toys"]


# --- Edge cases and combination ----------------------------------------------

def test_empty_input():
    result = build_report([], settings())
    assert result == {"categories": [], "record_count": 0,
                      "category_count": 0, "dropped": 0}


def test_all_invalid_input():
    records = [record(id=""), record(category=""), record(day=1.5)]
    result = build_report(records, settings())
    assert result["dropped"] == 3
    assert result["record_count"] == 0
    assert result["categories"] == []
    assert result["category_count"] == 0


def test_full_pipeline_combined():
    records = [
        record(id="a", category="grocery", amount=100, day=15,
               status="posted"),
        record(id="b", category="dining", amount=60, day=12,
               status="cleared"),
        record(id="c", category="fuel", amount=30, day=18, status="posted"),
        record(id="d", category="toys", amount=200, day=11, status="posted"),
        record(id="", category="food", amount=50, day=15, status="posted"),
        record(id="e", category="grocery", amount=999, day=5,
               status="posted"),
        record(id="f", category="food", amount=999, day=15, status="void"),
    ]
    result = build_report(records, settings(sort_by="category"))
    assert result["dropped"] == 1
    assert result["record_count"] == 4
    assert result["category_count"] == 2
    assert result["categories"] == [
        {"category": "food", "total": 160.0},
        {"category": "toys", "total": 200.0},
    ]
