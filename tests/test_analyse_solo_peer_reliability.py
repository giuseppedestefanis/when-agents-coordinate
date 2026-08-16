"""Tests for the §5.5 additions in scripts/analyse_solo_peer_reliability.py:
the exact-permutation reliability column and the collection-gap timing helpers.
"""

from __future__ import annotations

import importlib.util
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_ROOT, "scripts",
                      "analyse_solo_peer_reliability.py")


def _import():
    spec = importlib.util.spec_from_file_location(
        "analyse_solo_peer_reliability", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, REPO_ROOT)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


M = _import()


def test_parse_cell_from_run_id():
    assert M.parse_cell_from_run_id(
        "family-1-process_orders-overlapping-a8-peer-mandatory-r05"
    ) == (8, "peer", "mandatory", "overlapping")
    assert M.parse_cell_from_run_id(
        "family-2-summarise_transactions-clean-a2-solo-forbidden-r10"
    ) == (2, "solo", "forbidden", "clean")
    assert M.parse_cell_from_run_id("not-a-run-id") is None
    # orchestrator parses too (filtered later as not a solo/peer draw)
    assert M.parse_cell_from_run_id(
        "family-1-process_orders-clean-a4-orchestrator-allowed-r01"
    ) == (4, "orchestrator", "allowed", "clean")


def test_run_start_times_takes_earliest_turn(tmp_path):
    turns = tmp_path / "turns.csv"
    turns.write_text(
        "run_id,agent,turn_uuid,timestamp\n"
        "runA,agent-1,u1,2026-05-23T10:00:05.000Z\n"
        "runA,agent-2,u2,2026-05-23T09:30:00.000Z\n"   # earliest for runA
        "runA,agent-1,u3,2026-05-23T11:00:00.000Z\n"
        "runB,agent-1,u4,2026-05-24T00:00:00.000Z\n")
    starts = M.run_start_times(str(turns))
    assert set(starts) == {"runA", "runB"}
    # runA start is the 09:30 turn, one hour (1800s? -> 30 min) before 10:00
    assert starts["runA"] < starts["runB"]
    assert abs((starts["runB"] - starts["runA"]) - (14.5 * 3600)) < 1.0


def test_exact_reframe_value_f2_borderline():
    """The §5.5 reframe number: the single Family-2 significant cell
    (2, mandatory, overlapping) — solo vs peer per-run n_agent_to_agent —
    drops from approx-significant to exact p=0.062 (>0.05). Locks the exact
    permutation result on the documented cell data."""
    solo = [3, 3, 4, 4, 4, 4, 4, 4, 4, 5]
    peer = [4, 4, 4, 4, 4, 5, 5, 5, 5, 5]
    p, _u, n = M.exact_mannwhitney_p(solo, peer)
    assert n == 184756                      # C(20,10)
    assert abs(p - 0.0616) < 1e-3
    assert p > 0.05                          # no longer significant under exact


def test_exact_f1_borderline_stays_significant():
    """Family-1 (8, mandatory, overlapping) stays significant under exact
    (~0.021), so F1 holds at 13/27."""
    solo = [0, 0, 0, 0, 0, 0, 13, 14, 24, 25]
    peer = [3, 9, 9, 15, 20, 21, 22, 34, 44, 54]
    p, _u, _n = M.exact_mannwhitney_p(solo, peer)
    assert abs(p - 0.0206) < 1e-3
    assert p < 0.05


def _mk_a2a_run(seconds):
    """A run whose only edges are agent_to_agent at the given second offsets."""
    return [{"timestamp": f"2026-01-01T00:00:{s:02d}+00:00",
             "edge_type": "agent_to_agent", "source": "a1", "target": "a2"}
            for s in seconds]


def test_decile_profile_reuse_and_diff():
    """§5.6 reuses the RQ2 decile machinery: a run's profile is per-decile
    counts; mean_profile averages per-run decile FRACTIONS; the comparison is
    the max per-decile |solo - peer|. Lock the definition on synthetic draws.
    """
    # solo: 10 a2a edges evenly spread over [0,9]s -> one per decile -> 0.1 each
    solo = [(None, M.run_metrics(_mk_a2a_run(range(10))))]
    # peer: 9 edges at t=0 (decile 0) + 1 at t=9 (decile 9) -> 0.9 / 0.1
    peer = [(None, M.run_metrics(_mk_a2a_run([0] * 9 + [9])))]
    sp = M.mean_profile(solo)["a2a"]
    pp = M.mean_profile(peer)["a2a"]
    assert abs(sp[0] - 0.1) < 1e-9
    assert abs(pp[0] - 0.9) < 1e-9 and abs(pp[9] - 0.1) < 1e-9
    max_diff = max(abs(sp[i] - pp[i]) for i in range(10))
    assert abs(max_diff - 0.8) < 1e-9
