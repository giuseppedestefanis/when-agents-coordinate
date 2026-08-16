"""Tests for the exact permutation Mann-Whitney helper in
scripts/analyse_pilot.py (the §5.4 pilot file-count contrasts).

At the pilot's N=6 per side with heavy ties, scipy's normal approximation is
unreliable; the exact permutation test enumerates all C(N, nx) assignments and
is ties-safe.
"""

from __future__ import annotations

import importlib.util
import math
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_ROOT, "scripts", "analyse_pilot.py")


def _import():
    spec = importlib.util.spec_from_file_location("analyse_pilot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, REPO_ROOT)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


M = _import()


def test_exact_complete_separation():
    """Fully separated groups: only the two extreme assignments match the
    observed deviation -> p = 2 / C(6,3) = 0.1."""
    p, u, n = M.exact_mannwhitney_p([1, 2, 3], [4, 5, 6])
    assert n == 20
    assert u == 0.0
    assert abs(p - 0.1) < 1e-9


def test_exact_family1_pilot_contrasts():
    """The §5.4:247 dataset is the FAMILY-1 pilot (process_orders). The n=4
    clean peer+orchestrator cells, n_file_nodes, N=6 per policy:
      forbidden [1,1,1,1,3,7], allowed [1,1,1,1,1,1], mandatory [5,5,5,6,6,6].
    Exact permutation: f-a ~0.45 (the reproducing 0.18 approx), f-m ~0.067,
    a-m ~0.0022. (An earlier executor pass mistakenly used the Family-2 pilot,
    which gives a wrong-family 1.00 for f-a; these are the verified values.)"""
    forb = [1, 1, 1, 1, 3, 7]
    allow = [1, 1, 1, 1, 1, 1]
    mand = [5, 5, 5, 6, 6, 6]
    p_fa, _, n = M.exact_mannwhitney_p(forb, allow)
    assert n == 924
    assert abs(p_fa - 0.4545) < 1e-3
    p_fm, _, _ = M.exact_mannwhitney_p(forb, mand)
    assert abs(p_fm - 0.0671) < 1e-3
    p_am, u_am, _ = M.exact_mannwhitney_p(allow, mand)
    assert u_am == 0.0                       # complete separation
    assert abs(p_am - 2.0 / 924.0) < 1e-9


def test_exact_two_sided_symmetric():
    """Swapping the two groups leaves the two-sided p unchanged."""
    a = M.exact_mannwhitney_p([1, 2, 3, 4], [2, 3, 4, 5])[0]
    b = M.exact_mannwhitney_p([2, 3, 4, 5], [1, 2, 3, 4])[0]
    assert abs(a - b) < 1e-12
    assert not math.isnan(a)
