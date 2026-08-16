"""Tests for scripts/analyse_chain_distance.py — the issue-6 chain-distance
attribution policy (directed -> agent step, role -> function step, broadcast
counted separately, self/unknown excluded)."""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_ROOT, "scripts", "analyse_chain_distance.py")


def _import():
    spec = importlib.util.spec_from_file_location("analyse_chain_distance",
                                                  SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, REPO_ROOT)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


M = _import()


def _write_instance(d):
    os.makedirs(os.path.join(d, "instance"))
    inst = {"agents": [
        {"agent_id": "agent-1", "components": [{"index": 0,
                                                "label": "Step: parse"}]},
        {"agent_id": "agent-2", "components": [{"index": 1,
                                                "label": "Step: validate"}]},
        {"agent_id": "agent-3", "components": [{"index": 2,
                                                "label": "Step: format"}]},
    ]}
    with open(os.path.join(d, "instance", "instance.json"), "w") as f:
        json.dump(inst, f)


def _write_edges(d, edges):
    os.makedirs(os.path.join(d, "datasets"))
    with open(os.path.join(d, "datasets", "edges.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["edge_type", "source", "target", "target_kind"])
        for row in edges:
            w.writerow(row)


def test_load_step_maps(tmp_path):
    d = str(tmp_path)
    _write_instance(d)
    agent_step, label_step = M.load_step_maps(
        os.path.join(d, "instance", "instance.json"))
    assert agent_step == {"agent-1": 0, "agent-2": 1, "agent-3": 2}
    assert label_step == {"parse": 0, "validate": 1, "format": 2}


def test_run_distances_attribution(tmp_path):
    d = str(tmp_path)
    _write_instance(d)
    _write_edges(d, [
        ("agent_to_agent", "agent-1", "agent-3", "canonical"),  # dist 2, +2
        ("agent_to_agent", "agent-3", "agent-1", "alias"),      # dist 2, -2
        ("agent_to_agent", "agent-2", "format", "role"),        # dist 1, +1
        ("agent_to_agent", "agent-1", "*", "broadcast"),        # broadcast
        ("agent_to_agent", "agent-2", "agent-2", "canonical"),  # self -> excl
        ("agent_to_agent", "agent-1", "ghost", "unknown"),      # unresolved
        ("agent_to_file", "agent-1", "f.py", ""),               # not a2a
    ])
    out = M.run_distances(d)
    assert out["directed"] == 3
    assert dict(out["dist"]) == {2: 2, 1: 1}
    assert out["broadcast"] == 1
    assert out["role_resolved"] == 1
    assert out["unresolved"] == 2          # the self-ref and the ghost target
    # direction: +2 (downstream), -2 (upstream), +1 (downstream)
    assert dict(out["signed"]) == {2: 1, -2: 1, 1: 1}


def test_run_distances_missing_files(tmp_path):
    assert M.run_distances(str(tmp_path)) is None
