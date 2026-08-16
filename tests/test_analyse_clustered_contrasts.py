"""Tests for scripts/analyse_clustered_contrasts.py — the draw-level
aggregation used by the issue-3 session-clustered contrasts."""

from __future__ import annotations

import importlib.util
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_ROOT, "scripts", "analyse_clustered_contrasts.py")


def _import():
    spec = importlib.util.spec_from_file_location("analyse_clustered_contrasts",
                                                  SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, REPO_ROOT)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


M = _import()


def _rows():
    # two (topology, pattern) draws at n=2/allowed, files 2,4 and 10,20
    return [
        {"n": 2, "topo": "peer", "pol": "allowed", "patt": "clean",
         "file": 2.0, "tokens": 100.0},
        {"n": 2, "topo": "peer", "pol": "allowed", "patt": "clean",
         "file": 4.0, "tokens": 200.0},
        {"n": 2, "topo": "solo", "pol": "allowed", "patt": "clean",
         "file": 10.0, "tokens": 50.0},
        {"n": 2, "topo": "solo", "pol": "allowed", "patt": "clean",
         "file": 20.0, "tokens": 50.0},
    ]


def test_draw_means_aggregates_per_session():
    dm = sorted(M.draw_means(_rows(), 2, "allowed", "file"))
    # peer/clean -> mean(2,4)=3 ; solo/clean -> mean(10,20)=15
    assert dm == [3.0, 15.0]


def test_run_vals_are_per_run():
    rv = sorted(M.run_vals(_rows(), 2, "allowed", "file"))
    assert rv == [2.0, 4.0, 10.0, 20.0]


def test_mw_welch_guards_small_samples():
    import math
    assert math.isnan(M._mw([1.0], []))         # empty side
    assert math.isnan(M._welch([1.0], [2.0]))   # <2 per side
    # a real contrast returns a finite p
    p = M._mw([1, 2, 3, 4], [10, 11, 12, 13])
    assert 0.0 <= p <= 1.0
