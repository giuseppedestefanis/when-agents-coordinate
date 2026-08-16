"""Tests for scripts/analyse_rq2_dynamics.py.

Exercise the per-run temporal metrics on synthetic edge lists with known
properties, plus the helpers (timestamp parsing, Gini). The metric
definitions are in memory/experiments/rq2-dynamics/analysis-plan.md.
"""

from __future__ import annotations

import importlib.util
import math
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(REPO_ROOT, "scripts", "analyse_rq2_dynamics.py")


def _import():
    spec = importlib.util.spec_from_file_location("analyse_rq2_dynamics",
                                                  SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, REPO_ROOT)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


M = _import()


def _edge(t, etype, src, tgt):
    """A minimal edge row at second offset t (within a fixed base minute)."""
    ts = f"2026-06-07T18:0{t // 60}:{t % 60:02d}.000000+00:00"
    return {"timestamp": ts, "edge_type": etype, "source": src, "target": tgt}


def test_parse_ts_both_iso_shapes():
    z = M.parse_ts("2026-05-29T16:15:03.387Z")
    off = M.parse_ts("2026-06-07T18:09:08.600802+00:00")
    assert z.year == 2026 and z.minute == 15
    assert off.second == 8


def test_gini_uniform_is_zero_and_concentrated_is_high():
    assert M._gini([5, 5, 5, 5]) == 0.0
    # one large gap dominating -> high concentration
    assert M._gini([0, 0, 0, 100]) > 0.6


def test_run_id_regex_is_family_agnostic():
    for rid in (
        "family-1-process_orders-clean-a4-peer-allowed-r01",
        "family-2-summarise_transactions-conflicting-a8-orchestrator-mandatory-r10",
    ):
        parts = M.parse_run_id(rid)
        assert parts is not None
    assert M.parse_run_id("not-a-run-id") is None


def test_run_metrics_basic_counts_and_phase_ordering():
    # a2a messages early (t=0,2), a2f writes late (t=8,10): com_a2a < com_a2f
    edges = [
        _edge(0, "agent_to_agent", "agent-1", "agent-2"),
        _edge(2, "agent_to_agent", "agent-2", "agent-1"),
        _edge(8, "agent_to_file", "agent-1", "f.py"),
        _edge(10, "agent_to_file", "agent-2", "g.py"),
    ]
    m = M.run_metrics(edges)
    assert m["n_edges"] == 4
    assert m["n_a2a"] == 2 and m["n_a2f"] == 2 and m["n_f2a"] == 0
    assert m["duration_s"] == 10.0
    assert m["com_a2a"] < m["com_a2f"]
    assert m["phase_gap"] > 0
    # four distinct edges, each fired once
    assert m["n_distinct_edges"] == 4
    assert m["frac_oneshot"] == 1.0
    assert m["max_recurrence"] == 1


def test_run_metrics_recurrence_and_lifespan():
    # the same edge fires at t=0 and t=10 -> recurrence 2, lifespan 1.0
    edges = [
        _edge(0, "agent_to_agent", "agent-1", "agent-2"),
        _edge(5, "agent_to_file", "agent-1", "f.py"),
        _edge(10, "agent_to_agent", "agent-1", "agent-2"),
    ]
    m = M.run_metrics(edges)
    assert m["max_recurrence"] == 2
    assert m["n_distinct_edges"] == 2          # (a1->a2 a2a) and (a1->f a2f)
    assert m["frac_oneshot"] == 0.5
    assert math.isclose(m["recurring_lifespan"], 1.0)


def test_run_metrics_too_few_edges_skips_rate_metrics():
    edges = [_edge(0, "agent_to_file", "agent-1", "f.py")]
    m = M.run_metrics(edges)
    assert m["n_edges"] == 1
    assert m["duration_s"] == 0.0
    assert "burstiness" not in m or math.isnan(m.get("burstiness", math.nan))


def test_burstiness_sign_regular_vs_bursty():
    # evenly spaced -> regular, B < 0
    regular = [_edge(t, "agent_to_file", "agent-1", f"f{t}.py")
               for t in (0, 5, 10, 15, 20)]
    assert M.run_metrics(regular)["burstiness"] < 0
    # clustered then one long gap -> bursty, B > 0
    bursty = [_edge(t, "agent_to_file", "agent-1", f"f{t}.py")
              for t in (0, 1, 2, 3, 40)]
    assert M.run_metrics(bursty)["burstiness"] > 0


def test_aggregate_phase_order_share():
    parts = M.parse_run_id(
        "family-2-summarise_transactions-clean-a4-peer-allowed-r01")
    # two runs: one with com_a2a<com_a2f, one without
    runs = [
        (parts, {"com_a2a": 0.2, "com_a2f": 0.6, "burstiness": 0.1,
                 "max_idle_gap_norm": 0.3, "gap_gini": 0.5, "phase_gap": 0.4,
                 "frac_oneshot": 0.5, "max_recurrence": 2,
                 "recurring_lifespan": 0.5, "n_distinct_edges": 4,
                 "n_edges": 8, "duration_s": 100.0}),
        (parts, {"com_a2a": 0.7, "com_a2f": 0.3, "burstiness": 0.0,
                 "max_idle_gap_norm": 0.2, "gap_gini": 0.4, "phase_gap": -0.4,
                 "frac_oneshot": 0.6, "max_recurrence": 1,
                 "recurring_lifespan": math.nan, "n_distinct_edges": 5,
                 "n_edges": 6, "duration_s": 80.0}),
    ]
    summary = M.aggregate(runs)
    key = (4, "peer", "allowed", "clean", "summarise_transactions")
    assert key in summary
    assert summary[key]["n_runs"] == 2
    assert math.isclose(summary[key]["phase_order_share"], 0.5)
