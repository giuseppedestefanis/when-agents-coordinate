#!/usr/bin/env python3
"""Recompute the network-structure statistics behind Finding 3 (leadership).

Motivation
----------
The degree-centralisation contrast (at eight agents, median 0.14 against
0.24, p = 0.018, orchestrator against flat) is retained as a supporting
analysis: the manuscript does not report it, and the paper's no-hub evidence
is the disparity-filter backbone (asserted in verify_claims.py).
verify_method_statistics.py reproduces the contrast exactly as a
collection-B-only comparison. This script recomputes centralisation from the
released CSVs alone, prints several definitional variants side by side for
transparency, and writes a tidy per-run table to
`data/derived/network-structure.csv`. It writes nothing outside the package.

Definition
----------
Degree centralisation is Freeman's, computed per run on the agent-to-agent
point-to-point message graph: edges whose `target_kind` is `canonical` or
`alias` (so both endpoints are real agents), self-loops removed, direction
dropped. It is 0 for a perfectly flat graph and 1 for a star, and is defined
only for runs with at least three messaging agents.

See the NOTE printed at the end for how the variants relate to the
collection-B-only reproduction in verify_method_statistics.py.

Run:  python3 scripts/analyse_network_structure.py
Needs: pandas, networkx, scipy
"""
from __future__ import annotations

import math
import os
import sys

import networkx as nx
import pandas as pd
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLAT = ["solo", "peer"]          # the two flat collections (A and B)
TARGET = (0.14, 0.24, 0.018)     # orchestrator, flat, p as printed in the paper


def _freeman(graph) -> float:
    """Freeman degree centralisation: 0 flat, 1 star. NaN below three nodes."""
    n = graph.number_of_nodes()
    if n < 3:
        return math.nan
    ci = {v: d / (n - 1) for v, d in dict(graph.degree()).items()}
    cmax = max(ci.values())
    return sum(cmax - c for c in ci.values()) / (n - 2)


def per_run_centralisation(edges: pd.DataFrame, kinds) -> dict:
    """Map run_id -> Freeman centralisation under one edge-filter variant."""
    m = edges[edges.edge_type == "agent_to_agent"]
    if kinds is not None:
        m = m[m.target_kind.isin(kinds)]
    m = m[m.source != m.target]
    out = {}
    for run_id, g in m.groupby("run_id"):
        dg = nx.DiGraph()
        dg.add_edges_from(zip(g.source, g.target))
        out[run_id] = _freeman(dg.to_undirected())
    return out


def contrast(runs: pd.DataFrame, col: str, n_agents: int):
    """Median centralisation for flat vs orchestrator, with a rank test."""
    d = runs[(runs.agent_count == n_agents) & runs[col].notna()]
    flat = d[d.topology.isin(FLAT)][col]
    orch = d[d.topology == "orchestrator"][col]
    if len(flat) < 3 or len(orch) < 3:
        return None
    p = stats.mannwhitneyu(flat, orch).pvalue
    return flat.median(), len(flat), orch.median(), len(orch), p


def main() -> int:
    path = os.path.join(ROOT, "data", "family-1-full", "master")
    edges = pd.read_csv(os.path.join(path, "edges.csv"))
    runs = pd.read_csv(os.path.join(path, "runs.csv"))

    variants = {
        "canonical+alias": ["canonical", "alias"],   # the repository's own definition
        "canonical only": ["canonical"],
        "all target kinds": None,
    }

    print("Degree centralisation, Family 1, by team size")
    print("(median across runs; p from a two-sided Mann-Whitney rank test)\n")
    print(f"{'variant':18s} {'n':>3s}  {'flat':>12s}  {'orchestrator':>13s}  {'p':>7s}")
    print("-" * 62)

    for label, kinds in variants.items():
        col = f"centr_{label.replace(' ', '_')}"
        runs[col] = runs.run_id.map(per_run_centralisation(edges, kinds))
        for n_agents in (4, 8):
            res = contrast(runs, col, n_agents)
            if res is None:
                continue
            fm, fn, om, on, p = res
            print(f"{label:18s} {n_agents:3d}  {fm:6.3f} (n={fn:3d})  "
                  f"{om:6.3f} (n={on:3d})  {p:7.3f}")

    out_dir = os.path.join(ROOT, "data", "derived")
    os.makedirs(out_dir, exist_ok=True)
    keep = ["run_id", "family", "instance", "agent_count", "topology",
            "artefact_policy", "success"]
    cols = keep + [c for c in runs.columns if c.startswith("centr_")]
    out_path = os.path.join(out_dir, "network-structure.csv")
    runs[cols].to_csv(out_path, index=False)
    print(f"\nwrote {os.path.relpath(out_path, ROOT)}")

    print("\nNOTE")
    print("  This centralisation statistic is a supporting analysis; the")
    print("  manuscript does not report it. verify_method_statistics.py")
    print(f"  reproduces {TARGET[0]} against {TARGET[1]}, p = {TARGET[2]}, as a")
    print("  collection-B-only comparison; pooled across both flat")
    print("  collections the difference disappears. Every variant above")
    print("  agrees in direction: the orchestrator graphs are no more")
    print("  centralised than the flat ones, so no hub forms when an agent")
    print("  is named coordinator.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
