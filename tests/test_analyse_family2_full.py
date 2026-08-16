"""Tests for the H2/H7 blessing additions in scripts/analyse_family2_full.py.

Covers the pure helpers added in the 2026-06-11 registry-audit closure:
  * benjamini_hochberg: step-up adjusted p-values, monotone, capped at 1.
  * the failing-test regex parsing used by the H7 verifier-re-run census.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(REPO_ROOT, "scripts", "analyse_family2_full.py")


def _import_analyse():
    spec = importlib.util.spec_from_file_location("analyse_family2_full",
                                                  SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, REPO_ROOT)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_bh_known_family():
    """The pre-registered F2 directional family resolves to the blessed
    values; in particular H2 raw 0.2886 -> p_BH 0.4330."""
    m = _import_analyse()
    fam = {
        "H4:f-m": 8.089e-29,
        "H4:a-m": 2.831e-25,
        "H6": 0.2297,
        "H2": 0.2886,
        "H4:f-a": 0.4659,
        "H3": 0.5,
    }
    adj = m.benjamini_hochberg(fam)
    # H2 raw 0.2886 at rank 4 of 6 -> 0.2886 * 6/4 = 0.4329 (full-precision
    # p=0.288626 gives 0.4330; both round to 0.433).
    assert round(adj["H2"], 3) == 0.433
    assert round(adj["H3"], 4) == 0.5000
    assert round(adj["H6"], 3) == 0.433         # tied up to H2 by monotonicity
    # tiny p-values stay significant after correction
    assert adj["H4:f-m"] < 1e-20
    assert adj["H4:a-m"] < 1e-20


def test_bh_monotone_and_capped():
    m = _import_analyse()
    adj = m.benjamini_hochberg({"a": 0.9, "b": 0.8, "c": 0.01})
    # adjusted values never exceed 1.0
    assert all(v <= 1.0 for v in adj.values())
    # the largest raw p keeps adjusted == raw
    assert round(adj["a"], 6) == 0.9
    # ranking order preserved: smaller raw p -> not larger adjusted p
    assert adj["c"] <= adj["b"] <= adj["a"]


def test_bh_single_element():
    m = _import_analyse()
    adj = m.benjamini_hochberg({"only": 0.04})
    assert round(adj["only"], 6) == 0.04


def test_failing_test_regex():
    """The census parses pytest -rfE FAILED/ERROR summary lines into bare
    test names and ignores everything else."""
    pattern = re.compile(r"^(?:FAILED|ERROR)\s+\S+::([A-Za-z0-9_]+)")
    sample = [
        "FAILED data/x/verifier/verifier.py::test_validate_zero_amount_kept - AssertionError",
        "FAILED /abs/verifier.py::test_end_to_end_zero_amount_record_included",
        "ERROR verifier.py::test_setup_thing",
        "23 passed, 2 failed in 0.41s",
        "PASSED verifier.py::test_should_be_ignored",
        "= short test summary info =",
    ]
    names = set()
    for line in sample:
        mm = pattern.match(line)
        if mm:
            names.add(mm.group(1))
    assert names == {
        "test_validate_zero_amount_kept",
        "test_end_to_end_zero_amount_record_included",
        "test_setup_thing",
    }


def test_h7_footprint_tests_constant():
    m = _import_analyse()
    assert m.H7_FOOTPRINT_TESTS == frozenset({
        "test_validate_zero_amount_kept",
        "test_end_to_end_zero_amount_record_included",
    })
