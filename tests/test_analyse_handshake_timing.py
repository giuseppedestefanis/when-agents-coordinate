"""Tests for scripts/analyse_handshake_timing.py -- the per-run timing
(tau placement, edge-arrival summary, broadcast augmentation, sustained
timing, exclusions)."""

from __future__ import annotations

import importlib.util
import math
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_ROOT, "scripts", "analyse_handshake_timing.py")


def _import():
    spec = importlib.util.spec_from_file_location(
        "analyse_handshake_timing", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, REPO_ROOT)
    sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
        sys.path.pop(0)
    return module


M = _import()


def _e(ts, src, tgt, kind, byte=100, tok=25):
    # build at minute `ts` of 2026-06-09T12:00; byte_size/token_cost as strings
    return {"timestamp": f"2026-06-09T12:{ts:02d}:00+00:00", "source": src,
            "target": tgt, "edge_type": "agent_to_agent", "target_kind": kind,
            "byte_size": str(byte), "token_cost": str(tok)}


def test_curve_summary_percentiles():
    # 10 pairs first-appearing at tau 0.0..0.9 -> tau50=0.4, tau90=0.8
    first = {f"p{i}": i / 10 for i in range(10)}
    s = M._curve_summary(first, "dir")
    assert math.isclose(s["tau50_dir"], 0.4)
    assert math.isclose(s["tau90_dir"], 0.8)
    assert math.isclose(s["tau_complete_dir"], 0.9)
    assert s["n_pairs_dir"] == 10
    # empty -> all None
    assert M._curve_summary({}, "dir")["tau50_dir"] is None


def test_run_timing_basic_and_tau():
    # n=2 roster; agents 1<->2 over a 10-minute window.
    edges = [
        _e(0, "agent-1", "agent-2", "canonical", byte=200),   # tau 0.0
        _e(5, "agent-2", "agent-1", "canonical", byte=100),   # tau 0.5
        _e(10, "agent-1", "agent-2", "canonical", byte=300),  # tau 1.0
    ]
    r = M.run_timing(edges, n=2)
    assert r is not None
    assert r["n_a2a"] == 3 and math.isclose(r["duration_s"], 600.0)
    # two distinct directed pairs (1->2, 2->1), both first-appear by tau 0.5
    assert r["n_directed_pairs"] == 2
    assert math.isclose(r["tau_complete_dir"], 0.5)   # 2->1 first at tau 0.5
    # 1->2 is sustained (2 msgs): 2nd message at tau 1.0, last at tau 1.0
    assert r["n_sustained_pairs"] == 1
    assert math.isclose(r["sustained_second_tau"], 1.0)
    assert math.isclose(r["sustained_last_tau"], 1.0)
    # mean byte_size = (200+100+300)/3
    assert math.isclose(r["mean_byte_size"], 200.0)


def test_run_timing_excludes_self_and_phantom():
    # agent-1 self-loop + addresses out-of-roster agent-3 at n=2; only 1->2 real
    edges = [
        _e(0, "agent-1", "agent-1", "canonical"),   # self
        _e(5, "agent-1", "agent-3", "canonical"),   # phantom (n=2)
        _e(10, "agent-1", "agent-2", "canonical"),  # real
    ]
    r = M.run_timing(edges, n=2)
    assert r["n_directed_pairs"] == 1                # only (agent-1, agent-2)
    assert r["n_a2a"] == 3                           # all still counted as a2a


def test_broadcast_augmentation():
    # a broadcast from agent-1 at tau 0 first-contacts agents 2,3,4 (n=4);
    # one later directed 1->2. Directed pairs = {1->2}; bcast pairs add 1->3,1->4
    edges = [
        _e(0, "agent-1", "*", "broadcast"),
        _e(5, "agent-2", "agent-3", "canonical"),
        _e(10, "agent-1", "agent-2", "canonical"),
    ]
    r = M.run_timing(edges, n=4)
    # directed: (2->3) and (1->2) = 2 pairs
    assert r["n_directed_pairs"] == 2
    # broadcast-inclusive pairs: directed 2 + (1->3),(1->4) from broadcast,
    # and (1->2) already directed -> total distinct = {2->3,1->2,1->3,1->4}=4
    assert r["n_pairs_bc"] == 4
    # broadcast lands at tau 0 -> bcast curve completes no later than directed
    assert r["tau90_bc"] <= r["tau90_dir"] + 1e-9


def test_exclusions():
    assert M.run_timing([_e(0, "agent-1", "agent-2", "canonical")], 2) is None
    # zero duration: 3 edges all at same timestamp
    same = [_e(0, "agent-1", "agent-2", "canonical") for _ in range(3)]
    assert M.run_timing(same, 2) is None


def test_tied_timestamps_do_not_crash():
    # two DISTINCT edges sharing a timestamp must not raise (sort by ts only);
    # a third edge later gives a non-zero duration so the run is included.
    rows = [
        _e(0, "agent-1", "agent-2", "canonical"),
        _e(0, "agent-2", "agent-1", "canonical"),   # same ts, different edge
        _e(5, "agent-1", "agent-2", "canonical"),
    ]
    r = M.run_timing(rows, n=2)
    assert r is not None and r["n_directed_pairs"] == 2
