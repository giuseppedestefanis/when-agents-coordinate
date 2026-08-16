"""Tests for scripts/analyse_classifier_accounting.py -- the target-kind
accounting (Outputs 1-2) and the chain-distance per-run aggregation helpers."""

from __future__ import annotations

import importlib.util
import math
import os
import sys
from collections import Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_ROOT, "scripts", "analyse_classifier_accounting.py")


def _import():
    spec = importlib.util.spec_from_file_location("analyse_classifier_accounting",
                                                  SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, REPO_ROOT)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


M = _import()


def _by_run():
    # run A: 8 canonical, 1 alias, 1 unknown (directed 9/10)
    # run B: 1 canonical, 1 broadcast, 1 role, 1 unknown (directed 1/4)
    return {
        "A": Counter({"canonical": 8, "alias": 1, "unknown": 1}),
        "B": Counter({"canonical": 1, "broadcast": 1, "role": 1, "unknown": 1}),
    }


def test_per_category_pooled_and_perrun():
    c = M.per_category(_by_run())
    # pooled: 14 edges, directed = (8+1)+(1) = 10 -> 10/14
    assert math.isclose(c["pooled_directed"], 10 / 14)
    # per-run mean directed = mean(9/10, 1/4)
    assert math.isclose(c["perrun_directed"], (0.9 + 0.25) / 2)
    # category shares sum to 1 within each estimator
    assert math.isclose(sum(c["pooled_share"].values()), 1.0)
    assert math.isclose(sum(c["perrun_share"].values()), 1.0)


def test_directed_bounds_monotone_and_floor():
    b = M.directed_bounds(_by_run())
    seq = [b[k]["perrun"] for k in
           ("base (can+alias)", "+unknown", "+unknown+role",
            "+unknown+role+broadcast")]
    # non-decreasing, and the all-category numerator is exactly 1.0
    assert all(x <= y + 1e-12 for x, y in zip(seq, seq[1:]))
    assert math.isclose(seq[-1], 1.0)
    # base equals the committed directed share
    assert math.isclose(b["base (can+alias)"]["perrun"],
                        M.per_category(_by_run())["perrun_directed"])


def test_load_cell_a2a_filters_cell_and_edge_type(tmp_path):
    runs = tmp_path / "runs.csv"
    runs.write_text(
        "run_id,agent_count,topology,artefact_policy,instance\n"
        "keep,4,peer,allowed,t/clean\n"        # in cell
        "drop_n,2,peer,allowed,t/clean\n"      # wrong agent_count
        "drop_i,4,peer,allowed,t/conflicting\n")  # wrong instance
    edges = tmp_path / "edges.csv"
    edges.write_text(
        "run_id,edge_type,target_kind\n"
        "keep,agent_to_agent,canonical\n"
        "keep,agent_to_file,\n"                 # not a2a, ignored
        "keep,agent_to_agent,broadcast\n"
        "drop_n,agent_to_agent,canonical\n")    # not in cell
    by_run = M.load_cell_a2a(str(runs), str(edges), "t/clean")
    assert set(by_run) == {"keep"}
    assert by_run["keep"] == Counter({"canonical": 1, "broadcast": 1})


def test_schedule_role_count(tmp_path):
    edges = tmp_path / "edges.csv"
    edges.write_text(
        "run_id,edge_type,target_kind\n"
        "r,agent_to_agent,canonical\n"
        "r,agent_to_agent,role\n"
        "r,agent_to_file,\n")
    n_role, n_a2a = M.schedule_role_count(str(edges))
    assert n_role == 1 and n_a2a == 2
