"""Tests for scripts/analyse_channel_scaling.py -- edge aggregation
(broadcast count, token-by-channel, fan-out, directed cross-check), record
assembly, and the scaling fit."""

from __future__ import annotations

import csv
import importlib.util
import math
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_ROOT, "scripts", "analyse_channel_scaling.py")
EDGE_COLS = ["run_id", "source", "target", "source_type", "target_type",
             "edge_type", "subtype", "timestamp", "token_cost", "byte_size",
             "turn_uuid", "tool", "target_kind"]


def _import():
    spec = importlib.util.spec_from_file_location("analyse_channel_scaling",
                                                  SCRIPT)
    m = importlib.util.module_from_spec(spec)
    sys.path.insert(0, REPO_ROOT)
    sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
    try:
        spec.loader.exec_module(m)
    finally:
        sys.path.pop(0)
        sys.path.pop(0)
    return m


M = _import()


def _edge(rid, src, tgt, et, tok, kind=""):
    st = {"agent_to_agent": ("agent", "agent"),
          "agent_to_file": ("agent", "file"),
          "file_to_agent": ("file", "agent")}[et]
    return {"run_id": rid, "source": src, "target": tgt, "source_type": st[0],
            "target_type": st[1], "edge_type": et, "subtype": "",
            "timestamp": "", "token_cost": str(tok), "byte_size": "",
            "turn_uuid": "", "tool": "", "target_kind": kind}


def _write(rows):
    fh = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="")
    w = csv.DictWriter(fh, fieldnames=EDGE_COLS)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    fh.close()
    return fh.name


def test_aggregate_edges_channels_and_fanout():
    rid = "r1"
    rows = [
        _edge(rid, "agent-1", "agent-2", "agent_to_agent", 10, "canonical"),
        _edge(rid, "agent-1", "agent-3", "agent_to_agent", 10, "alias"),
        _edge(rid, "agent-2", "*", "agent_to_agent", 5, "broadcast"),
        _edge(rid, "agent-2", "*", "agent_to_agent", 5, "broadcast"),
        _edge(rid, "agent-1", "fileA", "agent_to_file", 4),
        _edge(rid, "fileA", "agent-2", "file_to_agent", 2),
        _edge(rid, "fileA", "agent-3", "file_to_agent", 2),  # 2 readers
    ]
    path = _write(rows)
    try:
        out = M.aggregate_edges(path, {rid})
    finally:
        os.unlink(path)
    e = out[rid]
    assert e["M_bc"] == 2                      # two broadcast edges
    assert e["dir_edges"] == 2                 # canonical + alias
    assert math.isclose(e["tok_M"], 30.0)      # 10+10+5+5
    assert math.isclose(e["tok_W"], 4.0)
    assert math.isclose(e["tok_R"], 4.0)
    assert math.isclose(e["mean_readers_per_written_file"], 2.0)  # fileA: 2


def test_build_records_C_and_columns():
    meta = {"r1": {"n": 4, "topology": "peer", "policy": "allowed",
                   "M": 20.0, "M_dir": 12.0, "W": 5.0, "R": 9.0}}
    edge = {"r1": {"M_bc": 6, "tok_M": 100.0, "tok_W": 20.0, "tok_R": 30.0,
                   "mean_readers_per_written_file": 2.5, "dir_edges": 12}}
    recs = M.build_records(meta, edge)
    r = recs["r1"]
    assert r["C"] == 34.0                       # 20+5+9
    assert math.isclose(r["tok_C"], 150.0)
    assert r["M_dir"] == 12.0 and r["M_bc"] == 6


def test_fit_power_law_and_segment():
    # C = n^2 exactly -> slope 2.0, seg 2->4 = log2(16/4)=2.0
    recs = {f"r{n}": {"n": n, "topology": "peer", "policy": "allowed",
                      "C": float(n) ** 2} for n in (2, 4, 8)}
    fr = M.fit(recs, "peer", "allowed", "C")
    assert math.isclose(fr["slope"], 2.0, abs_tol=1e-9)
    assert math.isclose(fr["seg24"], 2.0, abs_tol=1e-9)
    assert math.isclose(fr["seg48"], 2.0, abs_tol=1e-9)


def test_cell_filter_separates_draws():
    recs = {"a": {"n": 2, "topology": "solo", "policy": "allowed", "C": 1},
            "b": {"n": 2, "topology": "peer", "policy": "allowed", "C": 2}}
    assert len(M.cell(recs, "solo", "allowed", 2)) == 1
    assert M.cell(recs, "solo", "allowed", 2)[0]["C"] == 1
