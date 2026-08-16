"""Tests for scripts/analyse_messaging_structure.py -- the per-run edge
aggregation (M/W/R/phi/file fan-out/effective out-degree), the disparity-filter
backbone, and the log-log fit helper."""

from __future__ import annotations

import csv
import importlib.util
import math
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_ROOT, "scripts", "analyse_messaging_structure.py")

EDGE_COLS = ["run_id", "source", "target", "source_type", "target_type",
             "edge_type", "subtype", "timestamp", "token_cost", "byte_size",
             "turn_uuid", "tool", "target_kind"]


def _import():
    spec = importlib.util.spec_from_file_location(
        "analyse_messaging_structure", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, REPO_ROOT)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


M = _import()


def _edge(rid, src, tgt, st, tt, et, tok, kind=""):
    return {"run_id": rid, "source": src, "target": tgt, "source_type": st,
            "target_type": tt, "edge_type": et, "subtype": "",
            "timestamp": "", "token_cost": tok, "byte_size": "",
            "turn_uuid": "", "tool": "", "target_kind": kind}


def _write_edges(rows):
    fh = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, newline="")
    w = csv.DictWriter(fh, fieldnames=EDGE_COLS)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    fh.close()
    return fh.name


def test_aggregate_edges_counts_and_fanout():
    rid = "r1"
    rows = [
        # direct messages: agent-1 -> agent-2 x3, agent-1 -> agent-3 x1
        _edge(rid, "agent-1", "agent-2", "agent", "agent",
              "agent_to_agent", "1.0", "canonical"),
        _edge(rid, "agent-1", "agent-2", "agent", "agent",
              "agent_to_agent", "1.0", "canonical"),
        _edge(rid, "agent-1", "agent-2", "agent", "agent",
              "agent_to_agent", "1.0", "canonical"),
        _edge(rid, "agent-1", "agent-3", "agent", "agent",
              "agent_to_agent", "1.0", "canonical"),
        # a broadcast: not a directed peer
        _edge(rid, "agent-1", "everyone", "agent", "agent",
              "agent_to_agent", "1.0", "broadcast"),
        # writes: fileA x2 (agent-1), fileB x1 (agent-2)
        _edge(rid, "agent-1", "fileA", "agent", "file",
              "agent_to_file", "2.0"),
        _edge(rid, "agent-1", "fileA", "agent", "file",
              "agent_to_file", "2.0"),
        _edge(rid, "agent-2", "fileB", "agent", "file",
              "agent_to_file", "2.0"),
        # reads: fileA read by agent-2 and agent-3 (shared), fileB by agent-1
        _edge(rid, "fileA", "agent-2", "file", "agent",
              "file_to_agent", "3.0"),
        _edge(rid, "fileA", "agent-3", "file", "agent",
              "file_to_agent", "3.0"),
        _edge(rid, "fileB", "agent-1", "file", "agent",
              "file_to_agent", "3.0"),
    ]
    path = _write_edges(rows)
    try:
        out = M.aggregate_edges(path, {rid})
    finally:
        os.unlink(path)
    m = out[rid]
    assert m["M"] == 5 and m["W"] == 3 and m["R"] == 3
    assert m["tok_M"] == 5.0 and m["tok_W"] == 6.0 and m["tok_R"] == 9.0
    assert m["C"] == 11
    assert math.isclose(m["phi"], 1.0)
    # fileA read by 2 agents (shared), fileB by 1 (private)
    assert m["n_shared_files"] == 1 and m["n_private_files"] == 1
    # readers per written file: fileA->2, fileB->1, mean 1.5
    assert math.isclose(m["mean_readers_per_written_file"], 1.5)
    # reads landing on shared files = 2 of 3
    assert math.isclose(m["broadcast_read_share"], 2.0 / 3.0)
    # only agent-1 is a directed sender; targets agent-2(3), agent-3(1)
    assert math.isclose(m["eff_outdeg"][1], 2.0)   # both peers
    assert math.isclose(m["eff_outdeg"][2], 1.0)   # only agent-2 has >=2
    assert math.isclose(m["eff_outdeg"][3], 1.0)   # only agent-2 has >=3
    assert math.isclose(m["eff_outdeg"][5], 0.0)   # none have >=5
    # locked numerator/denominators: deg_sum, n_qual, n_active, n_directed
    assert m["deg_sum"][1] == 2 and m["deg_sum"][2] == 1
    assert m["n_qual"][1] == 1 and m["n_qual"][2] == 1 and m["n_qual"][5] == 0
    assert m["n_active"] == 1 and m["n_directed"] == 1


def test_effective_degree_denominators():
    # one run, 4 agents; agent-1 -> agent-2 x3, agent-1 -> agent-3 x2;
    # agent-2 -> agent-3 x1. directed degrees at t>=2: a1=2, a2=0.
    rid = "rE"
    rows = []

    def a2a(s, t, k):
        return _edge(rid, s, t, "agent", "agent", "agent_to_agent", "0", k)
    rows += [a2a("agent-1", "agent-2", "canonical")] * 3
    rows += [a2a("agent-1", "agent-3", "canonical")] * 2
    rows += [a2a("agent-2", "agent-3", "canonical")] * 1
    path = _write_edges(rows)
    try:
        out = M.aggregate_edges(path, {rid})
    finally:
        os.unlink(path)
    rec = out[rid]
    rec["n_agents"] = 4                       # merged from meta in build()
    # t>=2: agent-1 reaches agent-2 and agent-3 (both >=2) -> degree 2;
    # agent-2 reaches no peer with >=2 -> degree 0. deg_sum=2.
    assert rec["deg_sum"][2] == 2
    assert rec["n_directed"] == 2             # agent-1 and agent-2 sent directed
    assert rec["n_qual"][2] == 1              # only agent-1 sustains a peer
    # team-level: deg_sum / n_agents = 2/4 = 0.5
    assert math.isclose(M.eff_perrun(rec, 2, "team"), 0.5)
    # participant: deg_sum / n_qual = 2/1 = 2.0
    assert math.isclose(M.eff_perrun(rec, 2, "participant"), 2.0)
    # directed-sender: deg_sum / n_directed = 2/2 = 1.0
    assert math.isclose(M.eff_perrun(rec, 2, "directed"), 1.0)
    # zero-qualifier threshold returns None (guarded denominator)
    assert M.eff_perrun(rec, 5, "participant") is None


def test_self_and_phantom_excluded_from_degree():
    # n=2 roster {agent-1, agent-2}. agent-1 addresses itself, a phantom
    # agent-0, and the real peer agent-2. Only agent-2 should count.
    rid = "rP"
    rows = [
        _edge(rid, "agent-1", "agent-1", "agent", "agent",
              "agent_to_agent", "1.0", "canonical"),   # self
        _edge(rid, "agent-1", "agent-0", "agent", "agent",
              "agent_to_agent", "1.0", "canonical"),   # phantom (out of roster)
        _edge(rid, "agent-1", "agent-2", "agent", "agent",
              "agent_to_agent", "1.0", "canonical"),   # real peer
        _edge(rid, "agent-1", "agent-2", "agent", "agent",
              "agent_to_agent", "1.0", "alias"),       # real peer again
    ]
    path = _write_edges(rows)
    try:
        out = M.aggregate_edges(path, {rid}, roster_n={rid: 2})
    finally:
        os.unlink(path)
    rec = out[rid]
    assert rec["M"] == 4                       # all 4 messages still counted
    assert rec["n_self"] == 1 and rec["n_phantom"] == 1
    # agent-1's only real peer is agent-2 (addressed twice) -> degree 1, not 3
    assert rec["deg_sum"][1] == 1 and rec["deg_sum"][2] == 1
    assert rec["n_directed"] == 1
    # without a roster, the phantom is kept but self is still dropped
    path2 = _write_edges(rows)
    try:
        out2 = M.aggregate_edges(path2, {rid})
    finally:
        os.unlink(path2)
    assert out2[rid]["deg_sum"][1] == 2       # agent-2 and agent-0 (no roster)
    assert out2[rid]["n_self"] == 1


def test_phi_dropped_when_no_writes():
    rid = "r2"
    rows = [
        _edge(rid, "agent-1", "agent-2", "agent", "agent",
              "agent_to_agent", "1.0", "canonical"),
        _edge(rid, "fileX", "agent-1", "file", "agent",
              "file_to_agent", "1.0"),  # a read with no writes
    ]
    path = _write_edges(rows)
    try:
        out = M.aggregate_edges(path, {rid})
    finally:
        os.unlink(path)
    assert out[rid]["phi"] is None          # W=0 guarded
    assert out[rid]["W"] == 0 and out[rid]["R"] == 1


def test_disparity_filter_uniform_vs_dominant():
    # uniform clique: no edge is significant (each carries an equal share)
    uniform = {("a", "b"): 1, ("a", "c"): 1, ("a", "d"): 1}
    assert M.disparity_backbone(uniform, 0.05) == set()
    assert M.disparity_backbone(uniform, 0.1) == set()
    # one dominant out-edge survives the filter
    dom = {("a", "b"): 10, ("a", "c"): 1, ("a", "d"): 1}
    keep = M.disparity_backbone(dom, 0.05)
    assert ("a", "b") in keep
    assert ("a", "c") not in keep and ("a", "d") not in keep


def test_fit_metric_recovers_power_law():
    # value = n^2 exactly -> log-log slope 2.0, zero residual -> tight CI
    by_n = {n: [{"M": float(n) ** 2}] for n in (2, 4, 8)}
    fit = M.fit_metric(by_n, "M")
    assert math.isclose(fit["slope"], 2.0, abs_tol=1e-9)
    assert math.isclose(fit["cm_slope"], 2.0, abs_tol=1e-9)
    assert math.isclose(fit["lo"], 2.0, abs_tol=1e-9)
    assert math.isclose(fit["hi"], 2.0, abs_tol=1e-9)
    # value = n^1 -> slope 1.0
    by_n1 = {n: [{"M": float(n)}] for n in (2, 4, 8)}
    assert math.isclose(M.fit_metric(by_n1, "M")["slope"], 1.0, abs_tol=1e-9)


def test_cell_mean_ignores_none():
    recs = [{"phi": 1.0}, {"phi": None}, {"phi": 3.0}]
    assert math.isclose(M.cell_mean(recs, "phi"), 2.0)
