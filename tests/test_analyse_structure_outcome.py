"""Tests for scripts/analyse_structure_outcome.py.

Cover the per-run structural battery (degree, proportions, asymmetry, and the
agent-agent subgraph metrics on the point-to-point projection), the Freeman
centralisation helper, and the ledger quality join. Definitions are in
memory/experiments/structure-outcome/analysis-plan.md.
"""

from __future__ import annotations

import importlib.util
import math
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_ROOT, "scripts", "analyse_structure_outcome.py")


def _import():
    spec = importlib.util.spec_from_file_location("analyse_structure_outcome",
                                                  SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, REPO_ROOT)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


M = _import()


def _e(etype, s, t, tk=""):
    return {"edge_type": etype, "source": s, "target": t, "target_kind": tk}


def _clique_a2a(agents):
    """Directed canonical messages between every ordered pair of agents."""
    return [_e("agent_to_agent", a, b, "canonical")
            for a in agents for b in agents if a != b]


def test_freeman_star_is_one_complete_is_zero():
    import networkx as nx
    star = nx.star_graph(3)            # 1 hub + 3 leaves
    assert math.isclose(M._freeman_degree_centralisation(star), 1.0)
    complete = nx.complete_graph(4)
    assert math.isclose(M._freeman_degree_centralisation(complete), 0.0)
    assert math.isnan(M._freeman_degree_centralisation(nx.path_graph(2)))


def test_clique_subgraph_density_clustering_centralisation():
    edges = _clique_a2a(["agent-1", "agent-2", "agent-3"])
    m = M.structural_metrics(edges)
    assert m["a2a_nodes"] == 3
    assert math.isclose(m["a2a_density"], 1.0)       # all pairs present
    assert math.isclose(m["a2a_clustering"], 1.0)    # one triangle
    assert math.isclose(m["a2a_centralisation"], 0.0)  # flat, no hub


def test_density_and_centralisation_bounded():
    # A range of shapes must never exceed 1 (the bug the fix closed).
    for agents in (["agent-1", "agent-2", "agent-3", "agent-4"],):
        m = M.structural_metrics(_clique_a2a(agents))
        assert 0.0 <= m["a2a_density"] <= 1.0
        assert 0.0 <= m["a2a_centralisation"] <= 1.0
        assert 0.0 <= m["a2a_clustering"] <= 1.0


def test_self_loops_and_broadcast_excluded_from_subgraph():
    edges = _clique_a2a(["agent-1", "agent-2", "agent-3"])
    edges.append(_e("agent_to_agent", "agent-1", "agent-1", "canonical"))  # self
    edges.append(_e("agent_to_agent", "agent-1", "*", "broadcast"))        # bcast
    edges.append(_e("agent_to_agent", "agent-2", "parse", "role"))         # role
    m = M.structural_metrics(edges)
    # subgraph still 3 agent nodes; self-loop/broadcast/role not added
    assert m["a2a_nodes"] == 3
    assert m["a2a_density"] <= 1.0
    # but the message counts include all of them
    assert m["n_a2a"] == 6 + 3
    assert math.isclose(m["prop_broadcast"], 1 / 9)


def test_proportions_and_read_write_asymmetry():
    edges = [
        _e("agent_to_file", "agent-1", "f.py"),
        _e("agent_to_file", "agent-1", "g.py"),
        _e("file_to_agent", "f.py", "agent-2"),
        _e("file_to_agent", "f.py", "agent-2"),
        _e("file_to_agent", "g.py", "agent-1"),
        _e("agent_to_agent", "agent-1", "agent-2", "canonical"),
    ]
    m = M.structural_metrics(edges)
    assert m["n_a2f"] == 2 and m["n_f2a"] == 3 and m["n_a2a"] == 1
    assert math.isclose(m["prop_a2f"], 2 / 6)
    assert math.isclose(m["rw_asymmetry"], 3 / 2)   # reads / writes
    assert math.isclose(m["mean_file_in"], 1.0)     # 2 files, 1 write each
    assert math.isclose(m["mean_file_out"], 1.5)    # f.py read 2x, g.py 1x


def test_subgraph_undefined_below_three_agents():
    m = M.structural_metrics(_clique_a2a(["agent-1", "agent-2"]))
    assert m["a2a_nodes"] == 2
    assert not math.isnan(m["a2a_density"])          # density defined at n=2
    assert math.isnan(m["a2a_clustering"])           # triangles need n>=3
    assert math.isnan(m["a2a_centralisation"])


def test_centralisation_contrast_emits_pooled_row():
    import pandas as pd
    rows = []
    # orchestrator more distributed (low centr), peer more centralised (high)
    for i in range(6):
        rows.append({"agent_count": 8, "topology": "orchestrator",
                     "artefact_policy": "allowed", "a2a_centralisation": 0.10})
        rows.append({"agent_count": 8, "topology": "peer",
                     "artefact_policy": "allowed", "a2a_centralisation": 0.50})
    df = pd.DataFrame(rows)
    out = "\n".join(M.centralisation_contrast(df))
    assert "committed contrast" in out
    assert "| pooled |" in out
    # the separated groups should yield a small p
    import re
    m = re.search(r"\| pooled \|.*\| ([0-9.eE+-]+) \|\s*$",
                  [l for l in out.splitlines() if l.startswith("| pooled")][0])
    assert m is not None


def test_load_ledger_quality(tmp_path):
    import json
    led = {
        "r1": {"run_id": "r1", "status": "ok",
               "tests_passed": 18, "tests_failed": 6},
        "r2": {"run_id": "r2", "status": "ok",
               "tests_passed": 25, "tests_failed": 0},
        "r3": {"run_id": "r3", "status": "error"},
        "r4": {"run_id": "r4", "status": "ok",
               "tests_passed": 0, "tests_failed": 0},   # no tests -> nan
    }
    p = tmp_path / "ledger.json"
    p.write_text(json.dumps(led))
    ok, quality = M.load_ledger(str(p))
    assert ok == {"r1", "r2", "r4"}                  # error excluded
    assert math.isclose(quality["r1"], 18 / 24)
    assert math.isclose(quality["r2"], 1.0)
    assert math.isnan(quality["r4"])


def test_target_kind_share_ranges_pooled_edge():
    """5.1 share ranges use the pooled-edge (message-weighted) per-cell rule:
    a cell's share pools all its runs' edges before dividing, and the reported
    range is min-max across cells in the slice."""
    def a2a(tk):
        return _e("agent_to_agent", "a", "b", tk)
    by_run = {
        # cell A (n=4 peer mandatory clean): r01 2/10 broadcast, r02 4/10
        # -> pooled cell share = 6/20 = 30%
        "family-2-summarise_transactions-clean-a4-peer-mandatory-r01":
            [a2a("broadcast")] * 2 + [a2a("canonical")] * 8,
        "family-2-summarise_transactions-clean-a4-peer-mandatory-r02":
            [a2a("broadcast")] * 4 + [a2a("canonical")] * 6,
        # cell B (n=4 solo mandatory conflicting): 0/5 broadcast -> 0%
        "family-2-summarise_transactions-conflicting-a4-solo-mandatory-r01":
            [a2a("canonical")] * 5,
    }
    lines = M.target_kind_share_ranges(by_run)
    row = [ln for ln in lines if ln.startswith("| broadcast | n=4")]
    assert row, "expected a broadcast n=4 row"
    # two cells, pooled range 0.0% (cell B) to 30.0% (cell A)
    assert "| 2 |" in row[0]
    assert "0.0%-30.0%" in row[0]


def test_target_kind_share_ranges_excludes_zero_a2a_cells():
    """A run with no agent_to_agent edges contributes no cell share."""
    by_run = {
        "family-1-process_orders-clean-a8-solo-forbidden-r01":
            [_e("agent_to_file", "a", "f.py", "")],
    }
    lines = M.target_kind_share_ranges(by_run)
    # no broadcast/role rows emitted because no cell has a2a edges
    assert not [ln for ln in lines if ln.startswith("| broadcast")]
